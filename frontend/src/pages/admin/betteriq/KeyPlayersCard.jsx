/* BetterIQ — KeyPlayers showcase (the module's signature card).
 *
 * A Uiverse crypto-card-inspired, IQ-themed flick-through: a Segmented switch
 * across a club's danger players → a featured panel with an animated count-up
 * headline, a draw-in Sparkline of recent form, and the rule-based analyst read
 * (key note → plan → risk / confidence + a danger / "paper tiger?" alert badge).
 *
 * Wired to the real dossier shape: danger_batters / danger_bowlers carry
 * `recent_scores` (strings like '67*') for bats and `recent_wickets` (ints) for
 * bowlers, plus form / vs_us / risk / confidence / plan / key_note / alert.
 */
import { useState } from 'react'
import { Icon, CountUp, Sparkline, Tag, Segmented, surname, a2, runsPhrase, wktsPhrase } from './ui'

/* recent_scores may be strings ('67*', '12') — parse to ints for the sparkline */
function toInt(v) { const n = parseInt(String(v).replace(/[*]/g, ''), 10); return Number.isNaN(n) ? 0 : n }

/* Danger / "paper tiger?" alert — red for danger, amber for caution, with the
   rule-based reasons surfaced on hover + inline below. */
function AlertBadge({ alert }) {
  if (!alert?.level) return null
  const danger = alert.level === 'danger'
  const color = danger ? 'var(--pb-red)' : 'var(--pb-amber)'
  const reasons = (danger ? alert.danger : alert.caution) || []
  return (
    <span title={reasons.join(' · ')}
      className="iq-mono inline-flex items-center gap-1 font-bold uppercase whitespace-nowrap shrink-0"
      style={{ fontSize: 9.5, letterSpacing: '0.1em', padding: '3px 8px', borderRadius: 6,
        background: `color-mix(in srgb, ${color} 18%, transparent)`, color }}>
      <Icon name={danger ? 'flame' : 'info'} size={11} />{danger ? 'Danger' : 'Paper tiger?'}
    </span>
  )
}

export default function KeyPlayersCard({ title, subtitle, players, kind = 'bat' }) {
  const [sel, setSel] = useState(0)
  if (!players?.length) return null
  const list = players.slice(0, 5)
  const i = Math.min(sel, list.length - 1)
  const p = list[i]
  const n = list.length

  const isBat = kind === 'bat'
  const spark = isBat ? (p.recent_scores || []).map(toInt) : (p.recent_wickets || [])
  const headline = isBat ? p.runs : p.wickets
  const unit = isBat ? 'runs' : 'wickets'
  const sub = isBat ? `avg ${a2(p.average)} · SR ${a2(p.strike_rate)}` : `avg ${a2(p.average)} · econ ${a2(p.economy)}`
  const formLabel = p.form === 'hot' ? 'In form' : p.form === 'cold' ? 'Out of form' : null
  const formColor = p.form === 'hot' ? 'var(--pb-brand)' : p.form === 'cold' ? 'var(--pb-red)' : 'var(--pb-amber)'
  const vs = p.vs_us
  const riskColor = p.risk === 'high' ? 'var(--pb-red)' : p.risk === 'medium' ? 'var(--pb-amber)' : 'var(--pb-faint)'
  const recentStr = isBat
    ? (p.recent_scores || []).join(' · ')
    : (p.recent_wickets || []).join(' · ')

  return (
    <div className="iq-card overflow-hidden" style={{ borderColor: 'color-mix(in srgb, var(--pb-accent) 28%, transparent)' }}>
      <div className="relative p-5 md:p-6"
        style={{ background: 'linear-gradient(165deg, color-mix(in srgb, var(--pb-accent) 8%, transparent), transparent 55%)' }}>
        {/* header */}
        <div className="flex items-start justify-between gap-2 mb-4">
          <div className="min-w-0">
            <div className="iq-eyebrow" style={{ color: 'var(--pb-accent)' }}>{title}</div>
            {subtitle && <div className="text-pb-faint text-[11.5px] truncate mt-1">{subtitle}</div>}
          </div>
          <AlertBadge alert={p.alert} />
        </div>

        {/* segmented flick-through (by surname) */}
        <div className="mb-5">
          <Segmented sm value={i} onChange={setSel}
            options={list.map((pl, idx) => ({ value: idx, label: surname(pl.name) }))} />
        </div>

        {/* featured */}
        <div className="flex items-end justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="iq-display font-bold text-[20px] leading-tight truncate">{p.name}</span>
              {formLabel && (
                <span className="iq-mono shrink-0" style={{ fontSize: 9.5, padding: '2px 7px', borderRadius: 99,
                  background: `color-mix(in srgb, ${formColor} 16%, transparent)`, color: formColor }}>{formLabel}</span>
              )}
            </div>
            <div className="text-pb-faint text-[12.5px] mt-1 iq-num">{sub}</div>
          </div>
          <div className="text-right shrink-0">
            <div className="iq-headline" style={{ fontSize: 'clamp(38px,5vw,52px)', lineHeight: 0.9 }}>
              <CountUp value={headline || 0} />
              <span className="text-pb-faint" style={{ fontSize: 14, fontWeight: 500, marginLeft: 4 }}>{unit}</span>
            </div>
            {vs && (isBat
              ? (vs.runs ? <div className="text-pb-faint text-[11.5px] iq-num mt-1">{runsPhrase(vs.runs, vs.average)} vs us</div> : null)
              : (vs.wickets ? <div className="text-pb-faint text-[11.5px] iq-num mt-1">{wktsPhrase(vs.wickets, vs.average)} vs us</div> : null))}
          </div>
        </div>

        {/* draw-in sparkline */}
        <div className="mt-4 px-3 pt-3 pb-2" style={{ background: 'var(--pb-surface2)', borderRadius: 12 }}>
          <div className="flex items-center justify-between mb-1">
            <span className="iq-eyebrow" style={{ fontSize: 9 }}>Last {spark.length || 5}</span>
            <span className="iq-mono text-pb-faint truncate ml-2" style={{ fontSize: 10.5 }}>{recentStr || '—'}</span>
          </div>
          <Sparkline key={(p.player_id || i) + ':' + i} values={spark} h={48} dots stroke="var(--pb-accent)" />
        </div>

        {/* analyst read */}
        {(p.key_note || p.plan || p.risk || p.confidence) && (
          <div className="mt-4 pt-4" style={{ borderTop: '1px solid color-mix(in srgb, var(--pb-accent) 16%, transparent)' }}>
            {p.key_note && <div className="text-[13.5px] leading-snug">{p.key_note}</div>}
            {p.plan && (
              <div className="text-[12.5px] mt-2.5 leading-snug">
                <span className="text-pb-faint">Plan:</span> <span className="font-semibold">{p.plan}</span>
              </div>
            )}
            <div className="flex flex-wrap items-center gap-1.5 mt-2.5">
              {p.risk && (
                <span className="iq-mono uppercase" style={{ fontSize: 9, padding: '2px 6px', borderRadius: 5,
                  background: `color-mix(in srgb, ${riskColor} 16%, transparent)`, color: riskColor }}>{p.risk} risk</span>
              )}
              {p.confidence && (
                <span className="iq-mono uppercase text-pb-faint" style={{ fontSize: 9, padding: '2px 6px', borderRadius: 5, border: '1px solid var(--pb-hairline2)' }}>{p.confidence} conf</span>
              )}
              {p.alert?.level && (
                <Tag tone={p.alert.level === 'danger' ? 'red' : 'amber'}>
                  {((p.alert.level === 'danger' ? p.alert.danger : p.alert.caution) || []).join(' · ') || (p.alert.level === 'danger' ? 'Danger' : 'Caution')}
                </Tag>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
