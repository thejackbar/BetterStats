/* BetterIQ — shared player deep-dive cards.
   Extracted from PlayerTrends so the unified Player search renders the exact
   same deep dive (radar, reliability, conversion, milestones, selection value,
   batting style, by opposition/venue and the bowling deep dive). `DeepDiveTab`
   takes { detail, deep, bdeep, radar, radarLoading } — detail from
   api.iqTrendsPlayer, deep from api.iqPlayerDeepDive, bdeep from
   api.iqBowlerDeepDive, radar from api.iqPlayerRadar. */
import { useState, useEffect } from 'react'
import {
  SplitBar, StackedBar, Card, Note, Tag, Segmented, Empty, Delta, KV,
  a2, LoadingBar, fmtCount, fmtOvers, fmtPct, runsPhrase,
} from './ui'
import { Radar } from './viz'
import ScoutingCard from './ScoutingCard'

const num = (v, dash = '—') => (v === null || v === undefined ? dash : v)
const pct = (v) => fmtPct(v)
const TYPE_LABEL = { runs: 'runs', wickets: 'wickets', matches: 'games', catches: 'catches' }
const ACCENT = 'var(--pb-accent)'

export function PlayerRadarCard({ radar }) {
  const hasBat = radar?.bat && Array.isArray(radar.bat.values) && radar.bat.values.length
  const hasBowl = radar?.bowl && Array.isArray(radar.bowl.values) && radar.bowl.values.length
  const [side, setSide] = useState(hasBat ? 'bat' : 'bowl')
  useEffect(() => { setSide(hasBat ? 'bat' : 'bowl') }, [hasBat, hasBowl, radar])
  if (!hasBat && !hasBowl) return null
  const r = side === 'bat' && hasBat ? radar.bat : radar.bowl
  return (
    <Card eyebrow="profile vs squad average" title="Player radar"
      right={hasBat && hasBowl ? <Segmented sm value={side} onChange={setSide} options={[{ value: 'bat', label: 'Bat' }, { value: 'bowl', label: 'Bowl' }]} /> : null}>
      <div className="flex flex-col items-center">
        <Radar key={side} axes={r.axes} values={r.values} baseline={r.baseline || [50, 50, 50, 50, 50, 50]} size={250}
          legend={{ series: 'this player', baseline: 'squad average' }} />
      </div>
      <Note>Each axis normalised 0–100 against the squad average (the dashed ring at 50). Higher is better — bowling axes are inverted so the outer edge is always stronger.</Note>
    </Card>
  )
}

export function ReliabilityCard({ deep }) {
  const rel = deep?.reliability
  if (!rel) return null
  const ceiling = rel.ceiling || 1
  const tiers = [['Floor', rel.floor], ['Median', rel.median], ['Ceiling', rel.ceiling]]
  return (
    <Card eyebrow="innings range" title="Reliability" right={rel.profile ? <Tag tone="accent">{rel.profile}</Tag> : null}>
      <div className="iq-eyebrow mb-2">Percentiles (25th / 50th / 90th)</div>
      <div className="flex items-end gap-2 h-24">
        {tiers.map(([lab, v], i) => (
          <div key={lab} className="flex-1 flex flex-col items-center justify-end h-full">
            <span className="iq-num font-bold text-[15px] mb-1">{num(v, 0)}</span>
            <div className="w-full" style={{ height: `${Math.max(8, Math.round(((v || 0) / ceiling) * 100))}%`, background: i === 1 ? ACCENT : 'color-mix(in srgb, var(--pb-accent) 45%, var(--pb-surface3))', borderRadius: '6px 6px 0 0', minHeight: 8 }} />
            <span className="iq-eyebrow mt-1.5" style={{ fontSize: 8.5 }}>{lab}</span>
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-1 mt-3 text-[12px] text-pb-faint">
        {rel.failure_rate != null && <span>Fails (&lt;10): <span className="iq-num">{fmtPct(rel.failure_rate)}</span></span>}
        {rel.contribution_rate != null && <span>20+ contributions: <span className="iq-num">{fmtPct(rel.contribution_rate)}</span></span>}
      </div>
      <Note>Floor / median / ceiling are the 25th, 50th and 90th percentiles of their scores. A wider spread means more boom-or-bust.</Note>
    </Card>
  )
}

export function ConversionCard({ deep }) {
  const c = deep.conversion
  if (!c) return null
  const fiftyPlus = (c.fifties || 0) + (c.hundreds || 0)
  const segs = [
    { label: '<10', value: c.under_10, color: 'var(--pb-red)' },
    { label: '10–24', value: c.b10_24, color: 'var(--iq-c-amber)' },
    { label: '25–49', value: c.b25_49, color: 'var(--pb-dim)' },
    { label: '50+', value: fiftyPlus, color: ACCENT },
  ]
  return (
    <Card eyebrow="how he scores" title="Starts & conversion" right={<span className="text-pb-faint text-[12px]">{c.innings} innings</span>}>
      <SplitBar h={12} segments={segs} />
      <div className="grid grid-cols-3 gap-3 text-center mt-4">
        <div><div className="iq-headline iq-num" style={{ fontSize: 22 }}>{pct(c.start_pct)}</div><div className="iq-eyebrow mt-1" style={{ fontSize: 8.5 }}>reach 25</div></div>
        <div><div className="iq-headline iq-num" style={{ fontSize: 22 }}>{fmtPct(c.convert_25_to_50)}</div><div className="iq-eyebrow mt-1" style={{ fontSize: 8.5 }}>25 → 50</div></div>
        <div><div className="iq-headline iq-num" style={{ fontSize: 22 }}>{num(c.fifties, 0)}/{num(c.hundreds, 0)}</div><div className="iq-eyebrow mt-1" style={{ fontSize: 8.5 }}>50s / 100s</div></div>
      </div>
      {deep.dismissals?.length > 0 && (
        <>
          <div className="iq-eyebrow mt-5 mb-3">How he gets out</div>
          <StackedBar data={deep.dismissals.map(d => ({ type: d.type, count: d.pct, pct: d.pct }))} />
        </>
      )}
    </Card>
  )
}

export function MilestonesCard({ milestones }) {
  if (!milestones?.length) return null
  return (
    <Card eyebrow="milestones" title="Closing in on" accent>
      <div className="space-y-3">
        {milestones.map((m, i) => (
          <div key={i} className="flex items-center justify-between gap-3 py-1">
            <div className="min-w-0 flex-1">
              <div className="font-semibold text-[14px] leading-tight">{fmtCount(m.target)} {TYPE_LABEL[m.type] || m.type}</div>
              <div className="text-pb-faint text-[12px] mt-1">needs <span className="iq-num">{fmtCount(m.needed)}</span></div>
            </div>
            {m.eta_games ? <Tag tone="accent" className="shrink-0">~{m.eta_games} game{m.eta_games === 1 ? '' : 's'}</Tag> : null}
          </div>
        ))}
      </div>
    </Card>
  )
}

export function SelectionValueCard({ deep }) {
  const sv = deep.selection_value
  if (!sv) return null
  return (
    <Card eyebrow="impact" title="Selection value & match-ups">
      <div className="flex items-end gap-6 mb-4">
        <div><div className="iq-headline iq-num" style={{ fontSize: 30, color: 'var(--pb-brand)' }}>{fmtPct(sv.with?.win_pct)}</div><div className="iq-eyebrow mt-1">With him <span className="text-pb-faintest">· {sv.with?.games ?? 0} {sv.with?.games === 1 ? 'game' : 'games'}</span></div></div>
        <div><div className="iq-headline iq-num" style={{ fontSize: 30, color: 'var(--pb-red)' }}>{fmtPct(sv.without?.win_pct)}</div><div className="iq-eyebrow mt-1">Without <span className="text-pb-faintest">· {sv.without?.games ?? 0} {sv.without?.games === 1 ? 'game' : 'games'}</span></div></div>
        {sv.swing != null && <div className="ml-auto"><Delta value={sv.swing} suffix=" pts" /></div>}
      </div>
      {deep.by_position?.length > 0 && (
        <KV label="By position" value={deep.by_position.map(p => `${p.position} ${a2(p.average)}`).join(' · ')} />
      )}
      {deep.similar_players?.length > 0 && (
        <>
          <div className="iq-eyebrow mt-3 mb-1.5">Statistically similar</div>
          <div className="flex flex-wrap gap-2">
            {deep.similar_players.map(s => (
              <span key={s.player_id} className="text-[12.5px] px-2.5 py-1" style={{ background: 'var(--pb-surface2)', borderRadius: 99 }}>
                {s.name} <span className="iq-num text-pb-faint">{fmtPct(s.similarity)}</span>
              </span>
            ))}
          </div>
        </>
      )}
      <Note>Win % is the team's record in games he played vs games he missed. Similarity compares career batting/bowling average, strike rate and economy across the squad.</Note>
    </Card>
  )
}

export function BattingStyleCard({ deep }) {
  const bs = deep.batting_style, cx = deep.context
  if (!bs && !cx) return null
  return (
    <Card eyebrow="batting profile" title="Style & situation" right={bs?.profile ? <Tag tone="accent">{bs.profile}</Tag> : null}>
      {bs && (
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          {[['Strike rate', a2(bs.strike_rate)], ['Boundary %', fmtPct(bs.boundary_pct)], ['Balls/boundary', a2(bs.balls_per_boundary)], ['4s / 6s', `${num(bs.fours, 0)}/${num(bs.sixes, 0)}`]].map(([l, v]) => (
            <div key={l} className="text-center"><div className="iq-headline iq-num" style={{ fontSize: 20 }}>{v}</div><div className="iq-eyebrow mt-0.5" style={{ fontSize: 8.5 }}>{l}</div></div>
          ))}
        </div>
      )}
      {cx && (
        <div className="grid grid-cols-2 gap-3 mt-4">
          {[['In wins', cx.wins], ['In losses', cx.losses], ['Batting first', cx.bat_first], ['Chasing', cx.chasing]].map(([l, c]) => (
            <div key={l} className="p-2.5" style={{ background: 'var(--pb-surface2)', borderRadius: 12 }}>
              <div className="iq-eyebrow mb-0.5" style={{ fontSize: 9 }}>{l}</div>
              {c ? <div className="iq-num"><span className="iq-headline" style={{ fontSize: 18 }}>{c.average == null ? '—' : a2(c.average)}</span> <span className="text-pb-faintest text-[11px]">avg · {c.innings} inns</span></div> : <div className="text-pb-faintest text-[11px]">—</div>}
            </div>
          ))}
        </div>
      )}
      <Note>Boundary % is the share of runs from 4s and 6s. Dot-ball and ball-range splits need ball-by-ball data we don't hold.</Note>
    </Card>
  )
}

export function OppositionVenueCard({ deep }) {
  const hasOpp = deep.by_opposition?.best?.length > 0 || deep.by_opposition?.worst?.length > 0
  const hasVenue = deep.by_venue?.length > 0
  if (!hasOpp && !hasVenue) return null
  return (
    <Card eyebrow="splits" title="By opposition & venue">
      {hasOpp && (
        <div className="grid sm:grid-cols-2 gap-4 text-[13px]">
          <div>
            <div className="iq-eyebrow mb-1.5">Dominates</div>
            {deep.by_opposition.best.length ? deep.by_opposition.best.map(o => <div key={o.name} className="flex justify-between gap-2 py-0.5"><span className="truncate">{o.name}</span><span className="iq-num text-pb-faint whitespace-nowrap">{runsPhrase(o.runs, o.average)}</span></div>) : <Empty>—</Empty>}
          </div>
          <div>
            <div className="iq-eyebrow mb-1.5">Struggles vs</div>
            {deep.by_opposition.worst.length ? deep.by_opposition.worst.map(o => <div key={o.name} className="flex justify-between gap-2 py-0.5"><span className="truncate">{o.name}</span><span className="iq-num text-pb-faint whitespace-nowrap">{runsPhrase(o.runs, o.average)}</span></div>) : <Empty>—</Empty>}
          </div>
        </div>
      )}
      {hasVenue && (
        <div className={`overflow-x-auto -mx-1 iq-scroll ${hasOpp ? 'mt-4 pt-4' : ''}`} style={hasOpp ? { borderTop: '1px solid var(--pb-hairline)' } : undefined}>
          <table className="w-full text-[13px]">
            <thead><tr className="iq-eyebrow text-left" style={{ fontSize: 9 }}>
              <th className="py-1 px-1 font-medium">Ground</th>
              <th className="py-1 px-1 font-medium text-right">M</th>
              <th className="py-1 px-1 font-medium text-right">Runs</th>
              <th className="py-1 px-1 font-medium text-right">Bat avg</th>
              <th className="py-1 px-1 font-medium text-right">Wkts</th>
              <th className="py-1 px-1 font-medium text-right">Bowl avg</th>
            </tr></thead>
            <tbody>
              {deep.by_venue.map((v, i) => (
                <tr key={i} style={{ borderTop: '1px solid var(--pb-hairline)' }}>
                  <td className="py-1.5 px-1 truncate max-w-[200px]">{v.venue}</td>
                  <td className="py-1.5 px-1 text-right iq-num text-pb-faint">{fmtCount(v.games)}</td>
                  <td className="py-1.5 px-1 text-right iq-num">{fmtCount(v.total_runs)}</td>
                  <td className="py-1.5 px-1 text-right iq-num">{a2(v.batting_average)}</td>
                  <td className="py-1.5 px-1 text-right iq-num">{fmtCount(v.wickets)}</td>
                  <td className="py-1.5 px-1 text-right iq-num text-pb-faint">{a2(v.bowling_average)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

/* ── Bowling deep dive (within the Deep dive tab) ────────────────────────── */
export function BowlingDeepDive({ deep, bdeep }) {
  const hasProfile = deep?.bowling_profile
  const hasBdeep = bdeep && bdeep.wickets > 0
  if (!hasProfile && !hasBdeep) return null
  return (
    <>
      <div className="flex items-center gap-3 mt-2 mb-1">
        <h3 className="iq-display font-bold text-[15px]" style={{ letterSpacing: '-0.01em' }}>Bowling deep dive</h3>
        <span className="flex-1 h-px" style={{ background: 'var(--pb-hairline)' }} />
      </div>

      <div className="grid gap-5 lg:grid-cols-2 items-start">
        {hasProfile && (() => {
          const bp = deep.bowling_profile
          const wp = deep.wickets_by_position || []
          const sumPos = (lo, hi) => wp.filter(r => r.batting_position >= lo && r.batting_position <= hi).reduce((a, r) => a + (r.wickets || 0), 0)
          const top = sumPos(1, 3), mid = sumPos(4, 7), low = sumPos(8, 13), tot = top + mid + low
          return (
            <Card eyebrow="career" title="Bowling profile">
              <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
                {[['Wkts', fmtCount(bp.total_wickets)], ['Avg', a2(bp.average)], ['Econ', a2(bp.economy)], ['S/R', a2(bp.bowling_strike_rate)], ['Best', bp.best_bowling_figures || '—'], ['5wi', num(bp.five_fors, 0)]].map(([l, v]) => (
                  <div key={l} className="text-center"><div className="iq-headline iq-num" style={{ fontSize: 20 }}>{v}</div><div className="iq-eyebrow mt-0.5" style={{ fontSize: 8.5 }}>{l}</div></div>
                ))}
              </div>
              {tot > 0 && (
                <div className="mt-4">
                  <div className="iq-eyebrow mb-2">Where the wickets come</div>
                  <SplitBar h={12} segments={[
                    { label: 'Top order (1–3)', value: top, color: ACCENT },
                    { label: 'Middle (4–7)', value: mid, color: 'var(--iq-c-amber)' },
                    { label: 'Lower (8–11)', value: low, color: 'var(--pb-dim)' },
                  ]} />
                  <div className="flex justify-between text-[11px] text-pb-faint mt-1.5">
                    <span>Top {fmtPct(100 * top / tot)}</span><span>Middle {fmtPct(100 * mid / tot)}</span><span>Lower {fmtPct(100 * low / tot)}</span>
                  </div>
                </div>
              )}
              {deep.bowling_dismissals?.length > 0 && (
                <div className="mt-4 pt-4" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
                  <div className="iq-eyebrow mb-2">How he takes wickets</div>
                  <div className="flex flex-wrap gap-2">
                    {deep.bowling_dismissals.map((d, i) => (
                      <span key={i} className="text-[12px] px-2.5 py-1 capitalize" style={{ background: 'var(--pb-surface2)', borderRadius: 99 }}>{d.dismissal_type} <span className="iq-num text-pb-faint">{d.count}</span></span>
                    ))}
                  </div>
                </div>
              )}
            </Card>
          )
        })()}

        {bdeep?.quality && (
          <Card eyebrow="who he dismisses" title="Wicket quality">
            <SplitBar h={12} segments={[
              { label: 'New (<10)', value: bdeep.quality.new, color: ACCENT },
              { label: 'Started (10–29)', value: bdeep.quality.started, color: 'var(--iq-c-amber)' },
              { label: 'Set (30+)', value: bdeep.quality.set, color: 'var(--pb-dim)' },
            ]} />
            <div className="grid grid-cols-3 gap-2 text-center mt-4">
              <div><div className="iq-headline iq-num" style={{ fontSize: 20 }}>{fmtPct(bdeep.quality.new_pct)}</div><div className="iq-eyebrow mt-0.5" style={{ fontSize: 8.5 }}>caught new</div></div>
              <div><div className="iq-headline iq-num" style={{ fontSize: 20 }}>{fmtPct(bdeep.quality.set_pct)}</div><div className="iq-eyebrow mt-0.5" style={{ fontSize: 8.5 }}>removed set</div></div>
              <div><div className="iq-headline iq-num" style={{ fontSize: 20 }}>{a2(bdeep.quality.scalp_value)}</div><div className="iq-eyebrow mt-0.5" style={{ fontSize: 8.5 }}>avg scalp</div></div>
            </div>
            <Note>"Set" = the batter had 30+ when dismissed; "new" = under 10. Avg scalp is the mean score of the batters he removed{bdeep.quality.ducks ? ` · ${bdeep.quality.ducks} duck${bdeep.quality.ducks === 1 ? '' : 's'} inflicted` : ''}.</Note>
          </Card>
        )}
      </div>

      {(bdeep?.fielders?.length > 0 || bdeep?.discipline) && (
        <div className="grid gap-5 lg:grid-cols-2 items-start">
          {bdeep?.fielders?.length > 0 && (
            <Card eyebrow="caught · stumped · run out" title="Who catches for him">
              <div className="flex flex-wrap gap-2">
                {bdeep.fielders.map((f, i) => (
                  <span key={i} className="text-[12px] px-2.5 py-1" style={{ background: 'var(--pb-surface2)', borderRadius: 99 }}>{f.name} <span className="iq-num text-pb-faint">×{f.count}</span></span>
                ))}
              </div>
            </Card>
          )}
          {bdeep?.discipline && (
            <Card eyebrow={`${fmtOvers(bdeep.discipline.overs)} overs`} title="Discipline">
              <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
                {[['Extras/over', a2(bdeep.discipline.extras_per_over)], ['Wides/over', a2(bdeep.discipline.wides_per_over)], ['Wides', fmtCount(bdeep.discipline.wides)], ['No-balls', fmtCount(bdeep.discipline.no_balls)]].map(([l, v]) => (
                  <div key={l} className="text-center"><div className="iq-headline iq-num" style={{ fontSize: 20 }}>{v}</div><div className="iq-eyebrow mt-0.5" style={{ fontSize: 8.5 }}>{l}</div></div>
                ))}
              </div>
              <Note>Extras (wides + no-balls) per over across his spells. Only shown where the scorecards record extras.</Note>
            </Card>
          )}
        </div>
      )}
    </>
  )
}

/* The scouting card section — manual batting/bowling intel for OUR player, the
   mirror of the opposition scout. Optional: only rendered when a saver is wired. */
function ScoutSection({ detail, deep, bdeep, scouting, onSaveScouting }) {
  if (!onSaveScouting) return null
  const hasBowling = (deep && deep.bowling_profile) || (bdeep && bdeep.wickets > 0)
  const hasBat = deep && deep.innings_count > 0
  const wicketMethods = (deep?.bowling_dismissals || []).map(d => ({ type: d.dismissal_type, count: d.count }))
  return (
    <>
      <div className="flex items-center gap-3 mt-2 mb-1">
        <h3 className="iq-display font-bold text-[15px]" style={{ letterSpacing: '-0.01em' }}>Scouting card</h3>
        <span className="flex-1 h-px" style={{ background: 'var(--pb-hairline)' }} />
      </div>
      <ScoutingCard keyId={detail?.player?.player_id}
        batting={scouting?.batting_intel} bowling={scouting?.bowling_intel}
        stats={{ dismissals: deep?.dismissals, wicketMethods }}
        defaultSide={hasBowling && !hasBat ? 'bowl' : 'bat'}
        onSave={onSaveScouting} />
    </>
  )
}

export function DeepDiveTab({ detail, deep, bdeep, radar, radarLoading, scouting = null, onSaveScouting = null }) {
  const hasDeep = deep && deep.innings_count > 0
  const hasBowling = (deep && deep.bowling_profile) || (bdeep && bdeep.wickets > 0)
  const scout = <ScoutSection detail={detail} deep={deep} bdeep={bdeep} scouting={scouting} onSaveScouting={onSaveScouting} />
  if (!hasDeep && !hasBowling && !radar?.bat && !radar?.bowl) {
    // No per-innings data — still let the scout record manual intel (the whole
    // point of the card is the read CA can't give us).
    return onSaveScouting
      ? <div className="space-y-5">{scout}<Note>Not enough per-innings data for the rest of the deep dive yet.</Note></div>
      : <Empty>Not enough per-innings data for a deep dive yet.</Empty>
  }
  return (
    <div className="space-y-5">
      {deep?.scouting_note && (
        <Card eyebrow="read" title="Scouting note" accent><div className="text-[13.5px] leading-relaxed">{deep.scouting_note}</div></Card>
      )}

      <div className="grid gap-5 lg:grid-cols-2 items-start">
        {radarLoading && !radar ? (
          <Card eyebrow="profile vs squad average" title="Player radar"><div className="py-16"><LoadingBar label="Building radar…" expectedMs={5000} /></div></Card>
        ) : <PlayerRadarCard radar={radar} />}
        {hasDeep && <ReliabilityCard deep={deep} />}
        {hasDeep && <ConversionCard deep={deep} />}
        <MilestonesCard milestones={detail.milestones} />
        {hasDeep && <SelectionValueCard deep={deep} />}
        {hasDeep && <BattingStyleCard deep={deep} />}
      </div>

      {hasDeep && <OppositionVenueCard deep={deep} />}

      <BowlingDeepDive deep={deep} bdeep={bdeep} />

      {scout}
    </div>
  )
}
