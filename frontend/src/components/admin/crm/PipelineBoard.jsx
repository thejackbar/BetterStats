import { useState } from 'react'
import { useToast } from '../../../contexts/ToastContext'
import { money, Pill, DEFAULT_CRM_TERMS, moduleLabel, sortModuleKeys, ONBOARDING_METHOD_LABELS } from './ui'

export const TIER_TONE = { HOT: 'red', WARM: 'amber', COLD: 'faint', NOT_INTERESTED: 'faint' }

// A Kanban-style pipeline board — one column per stage, drag-and-drop
// enabled (native HTML5 DnD, no library) between any two columns. `client`
// (the same scope-specific api.js bundle DealDetailModal takes) is what
// actually moves the deal on drop; `onMoved` lets the caller refresh its
// own state afterward. Clicking a card still opens the detail modal for
// everything DnD doesn't cover (won/lost, notes, contacts…). A stage's
// hide/show toggle (`client.updateStage`) lives here too, not just in
// ManageStagesModal, so a super admin can tidy the board without leaving it.
export default function PipelineBoard({ board, onOpenDeal, onMoved, client, terms }) {
  const toast = useToast()
  const [draggingId, setDraggingId] = useState(null)
  const [overStageId, setOverStageId] = useState(null)
  // Client-side only — "minimize" just narrows a column out of the way
  // visually, it doesn't hide it from the board (that's the separate,
  // persisted hidden_from_board flag below, still used for a stage nobody
  // wants on the board at all). Not persisted on purpose: a per-viewer
  // "get this out of my way for now" preference, not shared board state.
  const [minimized, setMinimized] = useState(() => new Set())
  if (!board) return null
  const { stages, totals } = board
  const visibleStages = stages.filter(s => !s.hidden_from_board)
  const hiddenStages = stages.filter(s => s.hidden_from_board)
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

  const setHidden = async (stageId, hidden) => {
    if (!client?.updateStage) return
    try {
      await client.updateStage(stageId, { hidden_from_board: hidden })
      onMoved?.()
    } catch (e) { toast.error(e.message || 'Could not update the stage') }
  }

  const toggleMinimized = (stageId) => {
    setMinimized(prev => {
      const next = new Set(prev)
      if (next.has(stageId)) next.delete(stageId); else next.add(stageId)
      return next
    })
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
      {hiddenStages.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 -mt-2">
          <span className="text-[11px] text-pb-faintest">Hidden from board (totals above still include them):</span>
          {hiddenStages.map(s => (
            <button key={s.id} onClick={() => setHidden(s.id, false)}
              className="px-2 py-0.5 rounded-full text-[10.5px] border border-pb-hairline2 text-pb-faint hover:text-pb-accent hover:border-pb-accent/50">
              {s.name} · show
            </button>
          ))}
        </div>
      )}

      <div className="flex gap-3 overflow-x-auto pb-2 items-start">
        {visibleStages.map(stage => {
          const isMin = minimized.has(stage.id)
          if (isMin) {
            return (
              <div key={stage.id} className="w-9 shrink-0"
                onDragOver={e => { if (draggingId) { e.preventDefault(); setOverStageId(stage.id) } }}
                onDragLeave={() => setOverStageId(id => (id === stage.id ? null : id))}
                onDrop={e => { e.preventDefault(); drop(stage.id) }}>
                <button onClick={() => toggleMinimized(stage.id)} title={`Expand ${stage.name}`}
                  className={`w-full pb-card px-1 py-2.5 flex flex-col items-center gap-2 hover:border-pb-accent/40 transition ${
                    overStageId === stage.id ? 'ring-2 ring-pb-accent/50 bg-pb-accent/5' : ''}`}>
                  <span className="text-pb-faint text-[13px] leading-none">›</span>
                  <span className="font-mono text-[10px] text-pb-faintest">{stage.deal_count}</span>
                  <span className="text-[11px] font-display font-bold text-pb-faint"
                    style={{ writingMode: 'vertical-rl', textOrientation: 'mixed' }}>{stage.name}</span>
                </button>
              </div>
            )
          }
          return (
          <div key={stage.id} className="w-64 shrink-0"
            onDragOver={e => { if (draggingId) { e.preventDefault(); setOverStageId(stage.id) } }}
            onDragLeave={() => setOverStageId(id => (id === stage.id ? null : id))}
            onDrop={e => { e.preventDefault(); drop(stage.id) }}>
            <div className="flex items-center justify-between mb-2 px-1 gap-1.5">
              <div className="flex items-center gap-1.5 min-w-0">
                <h3 className="font-display font-bold text-[13px] truncate">{stage.name}</h3>
                <Pill>{stage.deal_count}</Pill>
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                {stage.value_cents > 0 && <span className="text-[11px] text-pb-faint">{money(stage.value_cents)}</span>}
                <span className="font-mono text-[10px] text-pb-faintest" title="Stage default probability">
                  {stage.default_probability}%
                </span>
                <button onClick={() => toggleMinimized(stage.id)} title="Minimize this column"
                  className="text-pb-faintest hover:text-pb-accent text-[13px] leading-none px-0.5">‹</button>
              </div>
            </div>
            <div className={`space-y-2 min-h-[60px] rounded-lg transition ${
              overStageId === stage.id ? 'ring-2 ring-pb-accent/50 bg-pb-accent/5' : ''}`}>
              {stage.deals.length === 0 && (
                <div className="pb-card px-3 py-4 text-center text-[11.5px] text-pb-faintest border-dashed">No {t.itemPlural}</div>
              )}
              {stage.deals.map(deal => {
                const baseCents = deal.value_cents || 0
                const effCents = deal.effective_value_cents ?? baseCents
                const discountCents = baseCents - effCents
                return (
                <div key={deal.id} draggable={!!client?.moveStage}
                  onDragStart={e => { setDraggingId(deal.id); e.dataTransfer.effectAllowed = 'move' }}
                  onDragEnd={() => { setDraggingId(null); setOverStageId(null) }}
                  onClick={() => onOpenDeal(deal.id)}
                  title={deal.is_customer ? 'Already a BetterCricket subscriber' : undefined}
                  className={`pb-card w-full text-left px-3 py-2.5 hover:border-pb-accent/40 transition cursor-pointer relative ${
                    deal.is_customer ? 'border-2 border-emerald-500/70 shadow-[0_2px_14px_-4px_rgba(16,185,129,0.55)]' : ''} ${
                    deal.status !== 'open' ? 'opacity-60' : ''} ${draggingId === deal.id ? 'opacity-40' : ''}`}>
                  <div className="font-medium text-[13px] truncate mb-1">{deal.title}</div>
                  {deal.point_of_contact_name && (
                    <div className="text-[11px] text-pb-faint truncate">{deal.point_of_contact_name}</div>
                  )}
                  {deal.onboarding_method && (
                    <div className="text-[10.5px] text-pb-faintest truncate mb-1">
                      {ONBOARDING_METHOD_LABELS[deal.onboarding_method] || deal.onboarding_method}
                    </div>
                  )}
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <span className="text-[12px] text-pb-faint">{money(effCents)}</span>
                    {discountCents > 0 && (
                      <span className="text-[10.5px] text-pb-amber" title="Discount applied">−{money(discountCents)}</span>
                    )}
                  </div>
                  {(deal.module_keys?.length > 0 || deal.engagement_score != null) && (
                    <div className="flex flex-wrap gap-1 mt-1.5">
                      {deal.engagement_score != null && (
                        <Pill tone={TIER_TONE[deal.engagement_tier] || 'faint'}>{deal.engagement_score}</Pill>
                      )}
                      {sortModuleKeys(deal.module_keys).map(k => {
                        const isSubscribed = (deal.subscribed_modules || []).includes(k)
                        const days = deal.trial_days_remaining?.[k]
                        return (
                          <Pill key={k} tone={isSubscribed ? 'faint' : 'accent'}>
                            {moduleLabel(k)}{!isSubscribed && days != null ? ` (${days})` : ''}
                          </Pill>
                        )
                      })}
                    </div>
                  )}
                  {deal.status === 'won' && <Pill tone="green">{t.won}</Pill>}
                  {deal.status === 'lost' && <Pill tone="red">{t.lost}</Pill>}
                </div>
              )})}
            </div>
          </div>
        )})}
      </div>
    </div>
  )
}
