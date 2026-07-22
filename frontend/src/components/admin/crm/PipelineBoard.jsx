import { money, Pill, DEFAULT_CRM_TERMS } from './ui'

// A Kanban-style pipeline board — one column per stage, cards inside. Stage
// changes happen from the deal detail modal's stage dropdown (opened by
// clicking a card) rather than drag-and-drop, which keeps this reliable with
// no browser-only interaction to get right without live testing.
export default function PipelineBoard({ board, onOpenDeal, terms }) {
  if (!board) return null
  const { stages, totals } = board
  const t = { ...DEFAULT_CRM_TERMS, ...terms }

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

      <div className="flex gap-3 overflow-x-auto pb-2">
        {stages.map(stage => (
          <div key={stage.id} className="w-64 shrink-0">
            <div className="flex items-center justify-between mb-2 px-1">
              <div className="flex items-center gap-1.5 min-w-0">
                <h3 className="font-display font-bold text-[13px] truncate">{stage.name}</h3>
                <Pill>{stage.deal_count}</Pill>
              </div>
              {stage.value_cents > 0 && <span className="text-[11px] text-pb-faint shrink-0">{money(stage.value_cents)}</span>}
            </div>
            <div className="space-y-2 min-h-[60px]">
              {stage.deals.length === 0 && (
                <div className="pb-card px-3 py-4 text-center text-[11.5px] text-pb-faintest border-dashed">No {t.itemPlural}</div>
              )}
              {stage.deals.map(deal => (
                <button key={deal.id} onClick={() => onOpenDeal(deal.id)}
                  className={`pb-card w-full text-left px-3 py-2.5 hover:border-pb-accent/40 transition ${deal.status !== 'open' ? 'opacity-60' : ''}`}>
                  <div className="font-medium text-[13px] truncate mb-1">{deal.title}</div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[12px] text-pb-faint">{money(deal.value_cents)}</span>
                    {deal.effective_probability != null && (
                      <span className="font-mono text-[10.5px] text-pb-faintest">{deal.effective_probability}%</span>
                    )}
                  </div>
                  {deal.module_keys && deal.module_keys.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1.5">
                      {deal.module_keys.map(k => <Pill key={k} tone="accent">{k}</Pill>)}
                    </div>
                  )}
                  {deal.status === 'won' && <Pill tone="green">{t.won}</Pill>}
                  {deal.status === 'lost' && <Pill tone="red">{t.lost}</Pill>}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
