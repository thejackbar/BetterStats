import { useState } from 'react'
import { useToast } from '../../../contexts/ToastContext'
import { money, Pill, DEFAULT_CRM_TERMS, moduleLabel, sortModuleKeys, ONBOARDING_METHOD_LABELS, townStateLabel, associationNames } from './ui'
import { CalendarIcon, eventSummaryText } from './EventForm'
import { moduleBrand } from '../../../lib/moduleBrand'

const BETTERSTATS_LOGO = moduleBrand('stats').logo

// Trial badge colours — bright amber for a club that self-registered its own
// trial, a pale/greyed amber for a trial a BetterCricket admin set up for the
// club. Same hourglass glyph either way; the colour carries the origin.
export const TRIAL_AMBER = '#F59E0B'
export const TRIAL_AMBER_MUTED = '#a6a39c'

export const TIER_TONE = { HOT: 'red', WARM: 'amber', COLD: 'faint', NOT_INTERESTED: 'faint' }

// A small solid arrow showing whether a club's engagement score moved since the
// previous calendar day: green up if it rose, red down if it fell, nothing if
// unchanged / not enough history (deal.engagement_delta_dir, set server-side
// from marketing_clubs.engagement_score_prev). Rendered right beside the score.
export function EngagementArrow({ dir }) {
  if (dir !== 'up' && dir !== 'down') return null
  const up = dir === 'up'
  return (
    <span title={`Engagement score ${up ? 'up' : 'down'} since yesterday`}
      className="text-[11px] leading-none font-bold select-none"
      style={{ color: up ? '#16c784' : '#ef4444' }}>
      {up ? '▲' : '▼'}
    </span>
  )
}

// The trial badge: a small amber hourglass shown top-right of a deal card when
// the club is registered and trialing at least one module but not yet paying
// for any (the subscriber logo takes precedence — see the board render). Amber
// matches the rest of the trial UI (TrialBanner, the days-remaining chips on
// this same card); a bright vs pale/greyed amber distinguishes a self-serve
// trial from one a BetterCricket admin set up. Inline SVG so it stays crisp at
// 16px.
export function TrialHourglassIcon({ className = '', color = TRIAL_AMBER }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" className={className}
      role="img" aria-label="On trial">
      <path d="M6 3h12" />
      <path d="M6 21h12" />
      <path d="M8 3v3.5a4 4 0 0 0 1.6 3.2L12 12l2.4-2.3A4 4 0 0 0 16 6.5V3" />
      <path d="M8 21v-3.5a4 4 0 0 1 1.6-3.2L12 12l2.4 2.3A4 4 0 0 1 16 17.5V21" />
    </svg>
  )
}

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

  // "Minimize this column" is now persisted per stage (like hidden_from_board
  // above), so a collapsed column stays collapsed across sessions rather than
  // resetting on every reload.
  const setMinimized = async (stageId, minimized) => {
    if (!client?.updateStage) return
    try {
      await client.updateStage(stageId, { minimized })
      onMoved?.()
    } catch (e) { toast.error(e.message || 'Could not update the stage') }
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

      <div className="flex gap-3 overflow-x-auto pb-2 items-stretch">
        {visibleStages.map(stage => {
          const isMin = !!stage.minimized
          if (isMin) {
            return (
              <div key={stage.id} className="w-9 shrink-0"
                onDragOver={e => { if (draggingId) { e.preventDefault(); setOverStageId(stage.id) } }}
                onDragLeave={() => setOverStageId(id => (id === stage.id ? null : id))}
                onDrop={e => { e.preventDefault(); drop(stage.id) }}>
                <button onClick={() => setMinimized(stage.id, false)} title={`Expand ${stage.name}`}
                  className={`w-full h-full pb-card px-1 py-2.5 flex flex-col items-center gap-2 hover:border-pb-accent/40 transition ${
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
          <div key={stage.id} className="w-64 shrink-0 flex flex-col"
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
                <button onClick={() => setMinimized(stage.id, true)} title="Minimize this column"
                  className="text-pb-faintest hover:text-pb-accent text-[13px] leading-none px-0.5">‹</button>
              </div>
            </div>
            {/* flex-1 + min-h so this fills the WHOLE rest of the column (matching
                the tallest column, via items-stretch on the row above) — a short
                column must still be a full-height drop target, not just as tall as
                its own few cards, or a drag from a long column has nowhere to land
                once the target column's cards scroll out of the viewport. */}
            <div className={`flex-1 space-y-2 min-h-[60px] rounded-lg transition ${
              overStageId === stage.id ? 'ring-2 ring-pb-accent/50 bg-pb-accent/5' : ''}`}>
              {stage.deals.length === 0 && (
                <div className="pb-card px-3 py-4 text-center text-[11.5px] text-pb-faintest border-dashed">No {t.itemPlural}</div>
              )}
              {stage.deals.map(deal => {
                const baseCents = deal.value_cents || 0
                const effCents = deal.effective_value_cents ?? baseCents
                const discountCents = baseCents - effCents
                // Subscribed = actually paying for at least one module — the
                // precise field, not the looser is_customer ("has ever been
                // onboarded"). This is what earns the logo badge.
                const isSubscriber = (deal.subscribed_modules || []).length > 0
                // In trial for at least one module — min_trial_days_remaining
                // is the min over trial_days_remaining, so non-null ⇒ a live
                // module trial exists.
                const isTrialing = deal.min_trial_days_remaining != null
                // The hourglass reflects that the DEAL is a trial — shown when
                // ANY of these say so, independent of whether a module-trial
                // countdown exists (many staff-set trials have none, which is
                // why they previously showed no badge):
                //   - onboarding method is a trial (self-serve OR super-admin),
                //   - the deal sits in a Trial stage ('trial' or
                //     'self_serve_trial'),
                //   - a live module-trial countdown (min_trial_days_remaining),
                //   - a prospect-level Club Directory trial (prospect_trial).
                const method = deal.onboarding_method
                const inTrialStage = deal.stage_key === 'trial' || deal.stage_key === 'self_serve_trial'
                const showTrialBadge = !isSubscriber && (
                  method === 'self_serve_trial' || method === 'super_admin_trial' ||
                  inTrialStage || isTrialing || !!deal.prospect_trial)
                // Bright amber = the club self-registered its trial; pale amber
                // = a BetterCricket admin set it up. Self-serve is signalled by
                // the method (or the Self-Serve Trial stage when the method is
                // unset); everything else reads as staff-set.
                const isSelfServeTrial = method === 'self_serve_trial'
                  || (!method && deal.stage_key === 'self_serve_trial')
                // Onboarded-club context line (state + seasons/grades/players
                // + setup progress + active-since), shown once a club is a
                // subscriber or on trial — mirrors the All Clubs detail line.
                const cs = deal.club_stats
                const stateLine = (isSubscriber || isTrialing) ? [
                  deal.marketing_club_state,
                  cs && `${cs.seasons_count ?? 0} season${(cs.seasons_count ?? 0) === 1 ? '' : 's'}`,
                  cs && `${cs.grades_count ?? 0} grade${(cs.grades_count ?? 0) === 1 ? '' : 's'}`,
                  cs && `${cs.players_count ?? 0} player${(cs.players_count ?? 0) === 1 ? '' : 's'}`,
                  cs && cs.setup_total > 0 && `setup ${cs.setup_done}/${cs.setup_total}`,
                  cs && cs.active_since && `active since ${new Date(cs.active_since).toLocaleDateString('en-AU')}`,
                ].filter(Boolean).join(' · ') : ''
                return (
                <div key={deal.id} draggable={!!client?.moveStage}
                  onDragStart={e => { setDraggingId(deal.id); e.dataTransfer.effectAllowed = 'move' }}
                  onDragEnd={() => { setDraggingId(null); setOverStageId(null) }}
                  onClick={() => onOpenDeal(deal.id)}
                  className={`pb-card w-full text-left px-3 py-2.5 hover:border-pb-accent/40 transition cursor-pointer relative ${
                    (isSubscriber || showTrialBadge) ? 'pr-7' : ''} ${
                    deal.status !== 'open' ? 'opacity-60' : ''} ${draggingId === deal.id ? 'opacity-40' : ''}`}>
                  {isSubscriber ? (
                    <img src={BETTERSTATS_LOGO} alt="" title="Subscribed to a BetterCricket module"
                      className="absolute top-2 right-2 w-4 h-4 rounded shrink-0" />
                  ) : showTrialBadge && (
                    <span title={isSelfServeTrial
                        ? 'Self-serve trial (club registered itself)'
                        : 'Trial set up by a BetterCricket admin'}
                      className="absolute top-2 right-2 w-4 h-4 shrink-0">
                      <TrialHourglassIcon className="w-4 h-4"
                        color={isSelfServeTrial ? TRIAL_AMBER : TRIAL_AMBER_MUTED} />
                    </span>
                  )}
                  <div className="font-medium text-[13px] truncate mb-1">{deal.title}</div>
                  {townStateLabel(deal.marketing_club_suburb, deal.marketing_club_state) && (
                    <div className="text-[10.5px] text-pb-faintest -mt-0.5 mb-1">
                      {townStateLabel(deal.marketing_club_suburb, deal.marketing_club_state)}
                    </div>
                  )}
                  {associationNames(deal.marketing_club_associations).length > 0 && (
                    <div className="flex flex-wrap gap-1 mb-1.5">
                      {associationNames(deal.marketing_club_associations).map(n => (
                        <Pill key={n}>{n}</Pill>
                      ))}
                    </div>
                  )}
                  {deal.point_of_contact_name && (
                    <div className="text-[11px] text-pb-faint truncate">{deal.point_of_contact_name}</div>
                  )}
                  {deal.onboarding_method && (
                    <div className="text-[10.5px] text-pb-faintest truncate mb-1">
                      {ONBOARDING_METHOD_LABELS[deal.onboarding_method] || deal.onboarding_method}
                    </div>
                  )}
                  {!deal.stage_auto_locked && deal.status === 'open' && (
                    <div title="Stage still moves itself — a repeat Contact-Us enquiry or an engagement score over 70 can advance it. Move it by hand to stop that.">
                      <Pill>auto</Pill>
                    </div>
                  )}
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <span className="text-[12px] text-pb-faint">{money(effCents)}</span>
                    {discountCents > 0 && (
                      <span className="text-[10.5px] text-pb-amber" title="Discount applied">−{money(discountCents)}</span>
                    )}
                  </div>
                  {(deal.module_keys?.length > 0 || deal.engagement_score != null) && (
                    <div className="flex flex-wrap items-center gap-1 mt-1.5">
                      {deal.engagement_score != null && (
                        <span className="inline-flex items-center gap-0.5">
                          <Pill tone={TIER_TONE[deal.engagement_tier] || 'faint'}>{deal.engagement_score}</Pill>
                          <EngagementArrow dir={deal.engagement_delta_dir} />
                        </span>
                      )}
                      {sortModuleKeys(deal.module_keys).map(k => {
                        const isSubscribed = (deal.subscribed_modules || []).includes(k)
                        const days = deal.trial_days_remaining?.[k]
                        // days is signed (see crm.trial_days_remaining_by_club) —
                        // negative means the trial's end date has already
                        // passed, not just "due today" (0).
                        const expired = !isSubscribed && days != null && days < 0
                        return (
                          <Pill key={k} tone={expired ? 'red' : isSubscribed ? 'faint' : 'accent'}
                            title={expired ? `${moduleLabel(k)} trial expired ${Math.abs(days)} day${Math.abs(days) === 1 ? '' : 's'} ago` : undefined}>
                            {moduleLabel(k)}
                            {expired ? ` · EXPIRED (${Math.abs(days)} day${Math.abs(days) === 1 ? '' : 's'} ago)` : (!isSubscribed && days != null ? ` (${days})` : '')}
                          </Pill>
                        )
                      })}
                    </div>
                  )}
                  {stateLine && (
                    <div className="font-mono text-[9.5px] text-pb-faintest mt-1.5 leading-snug">{stateLine}</div>
                  )}
                  {/* Next scheduled event — a calendar/date-based summary, set
                      apart from the rest of the card in its own indigo colour
                      with a small calendar icon. A been-and-gone event past the
                      super-admin "stale" window greys out (mid-grey); a soonest
                      upcoming event always wins over any past one. */}
                  {deal.next_event && (
                    <div className="flex items-center gap-1 mt-1.5 text-[10.5px] leading-snug font-medium"
                      style={{ color: deal.next_event.stale ? '#9ca3af' : '#8b7cf6' }}
                      title={deal.next_event.stale ? 'Past event (no upcoming one scheduled)' : 'Next scheduled event'}>
                      <CalendarIcon />
                      <span className="truncate">{eventSummaryText(deal.next_event)}</span>
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
