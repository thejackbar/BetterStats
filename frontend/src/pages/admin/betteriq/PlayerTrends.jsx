/* BetterIQ — Player trends (v2 design).
   Form movers surfaced first (rising/sliding bat & bowl with Delta) + emerging
   players, then a player deep-dive with tabs:
     • Trajectory — AreaChart of runs/season + table, range-aware delta (dims
       out-of-range seasons when a season RANGE is active).
     • Deep dive — player Radar + reliability percentiles, conversion,
       milestones, selection value, similar players (+ the bowling deep dive).
     • Compare — pick two players → one overlaid Radar + a head-to-head career
       stat table, the stronger value highlighted per row.
   Reads the GLOBAL Season + Team filter (useIQFilter); all data is real
   (api.iqTrends*). ?player=<id> deep-links a player. Averages 2dp via a2(). */
import { useState, useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import IQLayout from '../../../components/admin/IQLayout'
import {
  Sparkline, SplitBar, StackedBar,
  Card, Stat, Note, Tag, Btn, Segmented, Search, Empty, surname,
  Tabs, PageIntro, Delta, Initials, KV, a2,
} from './ui'
import { Radar, AreaChart } from './viz'
import { useIQFilter, seasonsInRange } from './Context'
import { api } from '../../../lib/api'

const num = (v, dash = '—') => (v === null || v === undefined ? dash : v)
const pct = (v) => (v === null || v === undefined ? '—' : `${v}%`)
const TYPE_LABEL = { runs: 'runs', wickets: 'wickets', matches: 'games', catches: 'catches' }
const ACCENT = 'var(--pb-accent)'
const AMBER = 'var(--iq-c-amber)'

/* ── Form movers ─────────────────────────────────────────────────────────── */
function MoverList({ title, tone, items, kind, onPick }) {
  const color = tone === 'up' ? 'var(--pb-brand)' : 'var(--pb-red)'
  return (
    <div>
      <div className="iq-eyebrow mb-2.5" style={{ color }}>{title}</div>
      <div className="space-y-2">
        {(items || []).map((p) => {
          const delta = Number(p.latest) - Number(p.baseline)
          // For bowling, lower is better → invert the sign the Delta colours by.
          const dVal = kind === 'bowl' ? -delta : delta
          return (
            <button key={p.player_id} onClick={() => onPick(p.player_id)}
              className="w-full flex items-center justify-between gap-2 text-left transition-colors hover:text-pb-accent">
              <span className="font-medium text-[13.5px] truncate">{p.name}</span>
              <span className="flex items-center gap-2 shrink-0">
                <span className="iq-num text-pb-faint text-[12px] whitespace-nowrap">{a2(p.baseline)}→{a2(p.latest)}</span>
                <Delta value={dVal} decimals={2} />
              </span>
            </button>
          )
        })}
        {!items?.length && <Empty>—</Empty>}
      </div>
    </div>
  )
}

/* ── Current-season player picker (searchable, opens on focus) ───────────── */
function PlayerSearch({ players, onPick, placeholder = 'Search a player…' }) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const t = q.trim().toLowerCase()
  const matches = (t ? players.filter(p => (p.name || '').toLowerCase().includes(t)) : players).slice(0, 30)
  return (
    <div className="relative" onFocusCapture={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)}>
      <Search value={q} onChange={(v) => { setQ(v); setOpen(true) }} placeholder={placeholder} className="w-full" />
      {open && (
        <div className="absolute z-30 mt-1.5 w-full iq-card p-1.5 max-h-80 overflow-auto iq-scroll" style={{ boxShadow: 'var(--iq-card-shadow)' }}>
          {matches.length === 0 ? (
            <div className="px-2.5 py-2 text-pb-faint text-sm">{players.length === 0 ? 'No current-season players found.' : 'No match.'}</div>
          ) : matches.map(p => (
            <button key={p.player_id} type="button" onClick={() => { onPick(p.player_id); setQ(''); setOpen(false) }}
              className="w-full flex items-center justify-between gap-3 px-2.5 py-2 text-left transition" style={{ borderRadius: 8 }}
              onMouseEnter={e => { e.currentTarget.style.background = 'var(--pb-surface2)' }}
              onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}>
              <span className="font-medium text-[13.5px] truncate">{p.name}</span>
              <span className="iq-mono text-pb-faintest text-[11px] whitespace-nowrap">
                {p.matches}g{p.runs ? ` · ${p.runs}r @ ${a2(p.bat_avg)}` : ''}{p.wickets ? ` · ${p.wickets}w @ ${a2(p.bowl_avg)}` : ''}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

/* ── Trend summary (header + season / career snapshot) ───────────────────── */
function VerdictTags({ verdict }) {
  if (!verdict) return null
  const map = { rising: ['Rising', 'win'], declining: ['Declining', 'red'], steady: ['Steady', 'faint'] }
  const out = []
  if (verdict.batting && map[verdict.batting]) out.push(['bat', ...map[verdict.batting]])
  if (verdict.bowling && map[verdict.bowling]) out.push(['bowl', ...map[verdict.bowling]])
  if (!out.length) return null
  return (
    <span className="flex items-center gap-1.5">
      {out.map(([k, label, tone]) => <Tag key={k} tone={tone}>{k === 'bowl' ? 'Bowl ' : 'Bat '}{label}</Tag>)}
    </span>
  )
}

function TrendSummary({ detail }) {
  const b = detail.career?.batting || {}
  const recentBat = (detail.recent_form?.batting || [])
  const form5 = recentBat.map(x => x.runs)
  const formTxt = recentBat.map(x => (x.not_out ? `${x.runs}*` : x.runs)).join('  ')
  const peakBat = detail.peak?.batting
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-4">
        <Initials name={detail.player?.name} size={56} tone="accent" />
        <div>
          <h2 className="iq-headline" style={{ fontSize: 30 }}>{detail.player?.name}</h2>
          <div className="flex items-center gap-2 mt-1.5">
            <VerdictTags verdict={detail.verdict} />
            {detail.consistency != null && <span className="text-pb-faint text-[12.5px] whitespace-nowrap">Consistency ±{detail.consistency}</span>}
          </div>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-2 items-start">
        <Card eyebrow="career to date" title="Career">
          <div className="grid grid-cols-3 gap-y-4 gap-x-3">
            <Stat label="Runs" value={num(b.total_runs, 0)} />
            <Stat label="Average" value={Number(b.average) || 0} decimals={2} count={false} />
            <Stat label="100s / 50s" value={`${num(b.hundreds, 0)}/${num(b.fifties, 0)}`} />
            <Stat label="Wickets" value={num(detail.career?.bowling?.total_wickets, 0)} />
            <Stat label="Bowl avg" value={Number(detail.career?.bowling?.average) || 0} decimals={2} count={false} />
            <Stat label="Catches" value={num(detail.career?.fielding?.total_catches_non_wk, 0)} />
          </div>
        </Card>
        <Card eyebrow="recent form" title="Form & peak">
          <div className="px-3 pt-3 pb-2" style={{ background: 'var(--pb-surface2)', borderRadius: 12 }}>
            <div className="flex items-center justify-between mb-1">
              <span className="iq-eyebrow" style={{ fontSize: 9 }}>Last innings</span>
              <span className="iq-mono text-pb-faint" style={{ fontSize: 10.5 }}>{formTxt || '—'}</span>
            </div>
            {form5.length >= 2 ? <Sparkline key={detail.player?.name} values={form5} h={50} dots />
              : <div className="text-pb-faintest text-[11px] py-3">Not enough recent innings.</div>}
          </div>
          <div className="mt-4 space-y-0.5">
            {peakBat && <KV label="Best batting season" value={`${peakBat.season} · ${peakBat.runs} @ ${a2(peakBat.average)}`} />}
            {detail.peak?.bowling && <KV label="Best bowling season" value={`${detail.peak.bowling.season} · ${detail.peak.bowling.wickets}w @ ${a2(detail.peak.bowling.average)}`} />}
            {!peakBat && !detail.peak?.bowling && <Empty>Not enough history yet.</Empty>}
          </div>
        </Card>
      </div>
    </div>
  )
}

/* ── Tab: Trajectory (range-aware) ───────────────────────────────────────── */
function TrajectoryTab({ detail, ctx, seasons }) {
  const rows = detail.seasons || []
  const isRange = ctx?.season?.mode === 'range'
  // In-range season labels (matched against the detail rows by label/year/name).
  // Computed unconditionally (before any early return) to keep hook order stable.
  const inRangeKeys = useMemo(() => {
    if (!isRange) return null
    const set = new Set()
    for (const s of seasonsInRange(ctx, seasons)) {
      if (s.label) set.add(String(s.label))
      if (s.year != null) set.add(String(s.year))
      if (s.name) set.add(String(s.name))
    }
    return set
  }, [isRange, ctx, seasons])

  if (!rows.length) return <Empty>No season data.</Empty>

  const inRange = (s) => {
    if (!isRange || !inRangeKeys) return true
    const n = String(s.season_name || '')
    if (inRangeKeys.has(n)) return true
    // match on the short "24/25" tail or the 4-digit start year embedded in the name
    const tail = n.match(/(\d{2})\s*[/\-]\s*(\d{2})\b/)
    if (tail && inRangeKeys.has(`${tail[1]}/${tail[2]}`)) return true
    const yr = n.match(/(\d{4})/)
    if (yr && inRangeKeys.has(yr[1])) return true
    return false
  }

  const spanRows = rows.filter(inRange)
  const dRuns = spanRows.length > 1 ? (spanRows[spanRows.length - 1].total_runs || 0) - (spanRows[0].total_runs || 0) : 0
  const dAvg = spanRows.length > 1 ? (Number(spanRows[spanRows.length - 1].batting_average) || 0) - (Number(spanRows[0].batting_average) || 0) : 0

  return (
    <div className="grid gap-5 lg:grid-cols-[1.5fr_1fr] items-start">
      <Card eyebrow="runs per season" title="Trajectory" right={isRange ? <Delta value={dRuns} suffix=" runs" /> : null}>
        <AreaChart points={rows.map(s => s.total_runs || 0)} labels={rows.map(s => s.season_name)} h={190} />
        {isRange
          ? <Note>Over the selected range: <b style={{ color: 'var(--pb-text)' }}>{dRuns >= 0 ? '+' : ''}{dRuns} runs</b> and <b style={{ color: 'var(--pb-text)' }}>{dAvg >= 0 ? '+' : ''}{a2(dAvg)} average</b> across {spanRows.length} season{spanRows.length === 1 ? '' : 's'}.</Note>
          : <Note>Runs scored each season, oldest → newest. Switch the season filter to <b style={{ color: 'var(--pb-text)' }}>Compare</b> for a range delta.</Note>}
      </Card>
      <Card eyebrow="the numbers" title="Season by season">
        <div className="overflow-x-auto -mx-1 iq-scroll">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="iq-eyebrow text-left" style={{ fontSize: 9 }}>
                <th className="py-2 px-1 font-medium">Season</th>
                <th className="py-2 px-1 font-medium text-right">M</th>
                <th className="py-2 px-1 font-medium text-right">Runs</th>
                <th className="py-2 px-1 font-medium text-right">Avg</th>
                <th className="py-2 px-1 font-medium text-right">Wkts</th>
                <th className="py-2 px-1 font-medium text-right">Avg</th>
                <th className="py-2 px-1 font-medium text-right">Econ</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s, i) => {
                const on = inRange(s)
                return (
                  <tr key={i} style={{ borderTop: '1px solid var(--pb-hairline)', opacity: on ? 1 : 0.4 }}>
                    <td className="py-2 px-1 iq-mono text-pb-dim whitespace-nowrap">
                      <span className="inline-flex items-center gap-2">{s.season_name}{on && isRange && <span style={{ width: 6, height: 6, borderRadius: 99, background: ACCENT }} />}</span>
                    </td>
                    <td className="py-2 px-1 text-right iq-num text-pb-faint">{num(s.matches, 0)}</td>
                    <td className="py-2 px-1 text-right iq-num font-semibold">{num(s.total_runs, 0)}</td>
                    <td className="py-2 px-1 text-right iq-num">{a2(s.batting_average)}</td>
                    <td className="py-2 px-1 text-right iq-num font-semibold">{num(s.total_wickets, 0)}</td>
                    <td className="py-2 px-1 text-right iq-num">{a2(s.bowling_average)}</td>
                    <td className="py-2 px-1 text-right iq-num text-pb-faint">{a2(s.economy)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}

/* ── Tab: Deep dive ──────────────────────────────────────────────────────── */
function PlayerRadarCard({ radar }) {
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
        <Radar key={side} axes={r.axes} values={r.values} baseline={r.baseline || [50, 50, 50, 50, 50, 50]} size={250} />
      </div>
      <Note>Each axis normalised 0–100 against the squad average (the dashed ring at 50). Higher is better — bowling axes are inverted so the outer edge is always stronger.</Note>
    </Card>
  )
}

function ReliabilityCard({ deep }) {
  const rel = deep.reliability
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
        {rel.failure_rate != null && <span>Fails (&lt;10): <span className="iq-num">{rel.failure_rate}%</span></span>}
        {rel.contribution_rate != null && <span>20+ contributions: <span className="iq-num">{rel.contribution_rate}%</span></span>}
      </div>
      <Note>Floor / median / ceiling are the 25th, 50th and 90th percentiles of their scores. A wider spread means more boom-or-bust.</Note>
    </Card>
  )
}

function ConversionCard({ deep }) {
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
        <div><div className="iq-headline iq-num" style={{ fontSize: 22 }}>{c.convert_25_to_50 == null ? '—' : `${c.convert_25_to_50}%`}</div><div className="iq-eyebrow mt-1" style={{ fontSize: 8.5 }}>25 → 50</div></div>
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

function MilestonesCard({ milestones }) {
  if (!milestones?.length) return null
  return (
    <Card eyebrow="milestones" title="Closing in on" accent>
      <div className="space-y-3">
        {milestones.map((m, i) => (
          <div key={i} className="flex items-center justify-between gap-3 py-1">
            <div className="min-w-0 flex-1">
              <div className="font-semibold text-[14px] leading-tight">{m.target} {TYPE_LABEL[m.type] || m.type}</div>
              <div className="text-pb-faint text-[12px] mt-1">needs <span className="iq-num">{m.needed}</span></div>
            </div>
            {m.eta_games ? <Tag tone="accent" className="shrink-0">~{m.eta_games} game{m.eta_games === 1 ? '' : 's'}</Tag> : null}
          </div>
        ))}
      </div>
    </Card>
  )
}

function SelectionValueCard({ deep }) {
  const sv = deep.selection_value
  if (!sv) return null
  return (
    <Card eyebrow="impact" title="Selection value & match-ups">
      <div className="flex items-end gap-6 mb-4">
        <div><div className="iq-headline iq-num" style={{ fontSize: 30, color: 'var(--pb-brand)' }}>{sv.with?.win_pct ?? '—'}%</div><div className="iq-eyebrow mt-1">With him <span className="text-pb-faintest">· {sv.with?.games ?? 0}g</span></div></div>
        <div><div className="iq-headline iq-num" style={{ fontSize: 30, color: 'var(--pb-red)' }}>{sv.without?.win_pct ?? '—'}%</div><div className="iq-eyebrow mt-1">Without <span className="text-pb-faintest">· {sv.without?.games ?? 0}g</span></div></div>
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
                {s.name} <span className="iq-num text-pb-faint">{s.similarity}%</span>
              </span>
            ))}
          </div>
        </>
      )}
      <Note>Win % is the team's record in games he played vs games he missed. Similarity compares career batting/bowling average, strike rate and economy across the squad.</Note>
    </Card>
  )
}

function BattingStyleCard({ deep }) {
  const bs = deep.batting_style, cx = deep.context
  if (!bs && !cx) return null
  return (
    <Card eyebrow="batting profile" title="Style & situation" right={bs?.profile ? <Tag tone="accent">{bs.profile}</Tag> : null}>
      {bs && (
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          {[['Strike rate', a2(bs.strike_rate)], ['Boundary %', bs.boundary_pct == null ? '—' : `${bs.boundary_pct}%`], ['Balls/boundary', num(bs.balls_per_boundary)], ['4s / 6s', `${num(bs.fours, 0)}/${num(bs.sixes, 0)}`]].map(([l, v]) => (
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

function OppositionVenueCard({ deep }) {
  const hasOpp = deep.by_opposition?.best?.length > 0 || deep.by_opposition?.worst?.length > 0
  const hasVenue = deep.by_venue?.length > 0
  if (!hasOpp && !hasVenue) return null
  return (
    <Card eyebrow="splits" title="By opposition & venue">
      {hasOpp && (
        <div className="grid sm:grid-cols-2 gap-4 text-[13px]">
          <div>
            <div className="iq-eyebrow mb-1.5">Dominates</div>
            {deep.by_opposition.best.length ? deep.by_opposition.best.map(o => <div key={o.name} className="flex justify-between gap-2 py-0.5"><span className="truncate">{o.name}</span><span className="iq-num text-pb-faint whitespace-nowrap">{o.runs} @ {a2(o.average)}</span></div>) : <Empty>—</Empty>}
          </div>
          <div>
            <div className="iq-eyebrow mb-1.5">Struggles vs</div>
            {deep.by_opposition.worst.length ? deep.by_opposition.worst.map(o => <div key={o.name} className="flex justify-between gap-2 py-0.5"><span className="truncate">{o.name}</span><span className="iq-num text-pb-faint whitespace-nowrap">{o.runs} @ {a2(o.average)}</span></div>) : <Empty>—</Empty>}
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
                  <td className="py-1.5 px-1 text-right iq-num text-pb-faint">{v.games}</td>
                  <td className="py-1.5 px-1 text-right iq-num">{v.total_runs}</td>
                  <td className="py-1.5 px-1 text-right iq-num">{a2(v.batting_average)}</td>
                  <td className="py-1.5 px-1 text-right iq-num">{v.wickets}</td>
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
function BowlingDeepDive({ deep, bdeep }) {
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
                {[['Wkts', num(bp.total_wickets, 0)], ['Avg', a2(bp.average)], ['Econ', a2(bp.economy)], ['S/R', a2(bp.bowling_strike_rate)], ['Best', bp.best_bowling_figures || '—'], ['5wi', num(bp.five_fors, 0)]].map(([l, v]) => (
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
                    <span>Top {Math.round(100 * top / tot)}%</span><span>Middle {Math.round(100 * mid / tot)}%</span><span>Lower {Math.round(100 * low / tot)}%</span>
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
              <div><div className="iq-headline iq-num" style={{ fontSize: 20 }}>{bdeep.quality.new_pct == null ? '—' : `${bdeep.quality.new_pct}%`}</div><div className="iq-eyebrow mt-0.5" style={{ fontSize: 8.5 }}>caught new</div></div>
              <div><div className="iq-headline iq-num" style={{ fontSize: 20 }}>{bdeep.quality.set_pct == null ? '—' : `${bdeep.quality.set_pct}%`}</div><div className="iq-eyebrow mt-0.5" style={{ fontSize: 8.5 }}>removed set</div></div>
              <div><div className="iq-headline iq-num" style={{ fontSize: 20 }}>{num(bdeep.quality.scalp_value)}</div><div className="iq-eyebrow mt-0.5" style={{ fontSize: 8.5 }}>avg scalp</div></div>
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
            <Card eyebrow={`${bdeep.discipline.overs} overs`} title="Discipline">
              <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
                {[['Extras/over', a2(bdeep.discipline.extras_per_over)], ['Wides/over', a2(bdeep.discipline.wides_per_over)], ['Wides', num(bdeep.discipline.wides, 0)], ['No-balls', num(bdeep.discipline.no_balls, 0)]].map(([l, v]) => (
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

function DeepDiveTab({ detail, deep, bdeep, radar, radarLoading }) {
  const hasDeep = deep && deep.innings_count > 0
  const hasBowling = (deep && deep.bowling_profile) || (bdeep && bdeep.wickets > 0)
  if (!hasDeep && !hasBowling && !radar?.bat && !radar?.bowl) {
    return <Empty>Not enough per-innings data for a deep dive yet.</Empty>
  }
  return (
    <div className="space-y-5">
      {deep?.scouting_note && (
        <Card eyebrow="read" title="Scouting note" accent><div className="text-[13.5px] leading-relaxed">{deep.scouting_note}</div></Card>
      )}

      <div className="grid gap-5 lg:grid-cols-2 items-start">
        {radarLoading && !radar ? (
          <Card eyebrow="profile vs squad average" title="Player radar"><div className="animate-pulse text-pb-faint text-sm py-16 text-center">Building radar…</div></Card>
        ) : <PlayerRadarCard radar={radar} />}
        <ReliabilityCard deep={deep} />
        {hasDeep && <ConversionCard deep={deep} />}
        <MilestonesCard milestones={detail.milestones} />
        {hasDeep && <SelectionValueCard deep={deep} />}
        {hasDeep && <BattingStyleCard deep={deep} />}
      </div>

      {hasDeep && <OppositionVenueCard deep={deep} />}

      <BowlingDeepDive deep={deep} bdeep={bdeep} />
    </div>
  )
}

/* ── Tab: Compare ────────────────────────────────────────────────────────── */
function radarSeries(payload, kind) {
  const r = payload?.[kind]
  if (!r || !Array.isArray(r.values) || !r.values.length) return null
  return r
}

function careerRows(A, B) {
  const ab = A?.career?.batting || {}, bb = B?.career?.batting || {}
  const abo = A?.career?.bowling || {}, bbo = B?.career?.bowling || {}
  // cmp: which side is "stronger" — null when equal/incomparable. lower=true for bowling avg.
  const cmp = (x, y, lower = false) => {
    const nx = Number(x), ny = Number(y)
    if (!isFinite(nx) || !isFinite(ny) || nx === ny) return null
    if (lower) return nx < ny ? 'a' : 'b'
    return nx > ny ? 'a' : 'b'
  }
  return [
    { label: 'Runs', a: num(ab.total_runs, 0), b: num(bb.total_runs, 0), better: cmp(ab.total_runs, bb.total_runs) },
    { label: 'Bat avg', a: a2(ab.average), b: a2(bb.average), better: cmp(ab.average, bb.average) },
    { label: '100s / 50s', a: `${num(ab.hundreds, 0)}/${num(ab.fifties, 0)}`, b: `${num(bb.hundreds, 0)}/${num(bb.fifties, 0)}`, better: cmp(ab.hundreds, bb.hundreds) },
    { label: 'Wickets', a: num(abo.total_wickets, 0), b: num(bbo.total_wickets, 0), better: cmp(abo.total_wickets, bbo.total_wickets) },
    { label: 'Bowl avg', a: a2(abo.average), b: a2(bbo.average), better: cmp(abo.average, bbo.average, true) },
  ]
}

function CompareRow({ label, a, b, better }) {
  const c = (s) => (better === s ? 'var(--pb-brand)' : 'var(--pb-text)')
  return (
    <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 py-2.5" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
      <div className="iq-num font-semibold text-right text-[15px]" style={{ color: c('a') }}>{a}</div>
      <div className="iq-eyebrow text-center" style={{ fontSize: 9, minWidth: 92 }}>{label}</div>
      <div className="iq-num font-semibold text-[15px]" style={{ color: c('b') }}>{b}</div>
    </div>
  )
}

function CompareTab({ aId, players, detailA }) {
  const [bId, setBId] = useState(null)
  const [radarA, setRadarA] = useState(null)
  const [radarB, setRadarB] = useState(null)
  const [detailB, setDetailB] = useState(null)

  // Default the opponent to the first picker player that isn't player A.
  useEffect(() => {
    if (bId || !players.length) return
    const first = players.find(p => p.player_id !== aId) || players[0]
    if (first) setBId(first.player_id)
  }, [players, aId, bId])

  useEffect(() => {
    let alive = true
    setRadarA(null)
    api.iqPlayerRadar(aId).then(d => { if (alive) setRadarA(d) }).catch(() => { if (alive) setRadarA(null) })
    return () => { alive = false }
  }, [aId])

  useEffect(() => {
    if (!bId) { setRadarB(null); setDetailB(null); return }
    let alive = true
    setRadarB(null); setDetailB(null)
    api.iqPlayerRadar(bId).then(d => { if (alive) setRadarB(d) }).catch(() => { if (alive) setRadarB(null) })
    api.iqTrendsPlayer(bId).then(d => { if (alive) setDetailB(d) }).catch(() => { if (alive) setDetailB(null) })
    return () => { alive = false }
  }, [bId])

  const nameA = detailA?.player?.name || surname(players.find(p => p.player_id === aId)?.name || '')
  const nameB = detailB?.player?.name || surname(players.find(p => p.player_id === bId)?.name || '')
  const ra = radarSeries(radarA, 'bat')
  const rb = radarSeries(radarB, 'bat')
  const rows = useMemo(() => careerRows(detailA, detailB), [detailA, detailB])

  return (
    <Card eyebrow="head to head" title="Compare players">
      <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-3 mb-5">
        <span className="iq-display font-semibold text-[14px] inline-flex items-center gap-2" style={{ color: ACCENT }}>
          <span style={{ width: 11, height: 11, borderRadius: 99, background: ACCENT }} />{nameA}
        </span>
        <span className="iq-mono text-pb-faint text-[12px]">vs</span>
        <div className="min-w-[220px]">
          <PlayerSearch players={players.filter(p => p.player_id !== aId)} onPick={setBId} placeholder="Pick a player to compare…" />
        </div>
      </div>

      {!bId ? (
        <Empty>Pick a second player to compare.</Empty>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[auto_1fr] items-center">
          <div className="flex flex-col items-center">
            {ra && rb
              ? <Radar key={aId + bId} axes={ra.axes} values={ra.values} compareValues={rb.values} compareColor={AMBER} size={260} />
              : <div className="text-pb-faint text-sm py-16 w-[260px] text-center">{radarA === null || radarB === null ? 'Loading radar…' : 'No batting radar to overlay for this pair.'}</div>}
            <div className="flex items-center gap-4 mt-2 text-[11.5px]">
              <span className="inline-flex items-center gap-1.5"><span style={{ width: 14, height: 3, background: ACCENT, borderRadius: 2 }} />{surname(nameA)}</span>
              <span className="inline-flex items-center gap-1.5"><span style={{ width: 14, height: 3, background: AMBER, borderRadius: 2 }} />{surname(nameB)}</span>
            </div>
          </div>
          <div>
            <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 pb-1">
              <div className="text-right font-bold iq-display truncate" style={{ color: ACCENT }}>{surname(nameA)}</div>
              <div style={{ minWidth: 92 }} />
              <div className="font-bold iq-display truncate" style={{ color: AMBER }}>{surname(nameB)}</div>
            </div>
            {detailB === null ? <div className="animate-pulse text-pb-faint text-sm py-6">Loading stats…</div>
              : rows.map(r => <CompareRow key={r.label} {...r} />)}
          </div>
        </div>
      )}
      <Note>Greener career figure is the stronger of the two. Radar axes are normalised against the squad average.</Note>
    </Card>
  )
}

/* ── Player detail (tabbed) ──────────────────────────────────────────────── */
function PlayerDetail({ playerId, players, ctx, seasons, onClear }) {
  const [detail, setDetail] = useState(null)
  const [deep, setDeep] = useState(null)
  const [bdeep, setBdeep] = useState(null)
  const [radar, setRadar] = useState(null)
  const [radarLoading, setRadarLoading] = useState(false)
  const [tab, setTab] = useState('trajectory')

  // Career radar (career = omit season) unless a single season is active.
  const seasonId = ctx?.season?.mode === 'single' ? (ctx?.season?.to?.id || undefined) : undefined

  useEffect(() => {
    if (!playerId) return
    let alive = true
    setDetail(null); setDeep(null); setBdeep(null)
    api.iqTrendsPlayer(playerId).then(d => { if (alive) setDetail(d) }).catch(() => { if (alive) setDetail({ error: true }) })
    api.iqPlayerDeepDive(playerId).then(d => { if (alive) setDeep(d) }).catch(() => { if (alive) setDeep(null) })
    api.iqBowlerDeepDive(playerId).then(d => { if (alive) setBdeep(d) }).catch(() => { if (alive) setBdeep(null) })
    return () => { alive = false }
  }, [playerId])

  useEffect(() => {
    if (!playerId) return
    let alive = true
    setRadar(null); setRadarLoading(true)
    api.iqPlayerRadar(playerId, seasonId)
      .then(d => { if (alive) setRadar(d) })
      .catch(() => { if (alive) setRadar(null) })
      .finally(() => { if (alive) setRadarLoading(false) })
    return () => { alive = false }
  }, [playerId, seasonId])

  if (detail === null) return <div className="iq-card p-6 animate-pulse text-pb-faint text-sm">Loading trajectory…</div>
  if (detail?.error) return <div className="iq-card p-6"><Empty>Couldn't load this player.</Empty></div>

  return (
    <div className="iq-fade space-y-6">
      <TrendSummary detail={detail} />

      <Tabs value={tab} onChange={setTab} tabs={[
        { value: 'trajectory', label: 'Trajectory' },
        { value: 'deep', label: 'Deep dive' },
        { value: 'compare', label: 'Compare' },
      ]} />

      {tab === 'trajectory' && <TrajectoryTab detail={detail} ctx={ctx} seasons={seasons} />}
      {tab === 'deep' && <DeepDiveTab detail={detail} deep={deep} bdeep={bdeep} radar={radar} radarLoading={radarLoading} />}
      {tab === 'compare' && <CompareTab aId={playerId} players={players} detailA={detail} />}
    </div>
  )
}

/* ── Overview (form movers + emerging + picker) ──────────────────────────── */
/* Squad filter chip — wraps to multiple rows (a club can field 16+ teams, which
   a single-row Segmented can't show without squashing the search bar). */
function SquadChip({ label, active, onClick }) {
  return (
    <button onClick={onClick} className="iq-display font-semibold text-[12.5px] transition whitespace-nowrap"
      style={{ padding: '6px 12px', borderRadius: 99,
        background: active ? 'color-mix(in srgb, var(--pb-accent) 16%, transparent)' : 'var(--pb-surface2)',
        color: active ? 'var(--pb-accent)' : 'var(--pb-dim)',
        border: `1px solid ${active ? 'color-mix(in srgb, var(--pb-accent) 40%, transparent)' : 'var(--pb-hairline2)'}` }}>{label}</button>
  )
}

function Overview({ overview, players, squads, squad, setSquad, pickerPlayers, onPick }) {
  const m = overview
  const noMovers = m && !m.batting?.risers?.length && !m.batting?.fallers?.length && !m.bowling?.risers?.length && !m.bowling?.fallers?.length
  const activeSquad = squads.find(s => s.id === squad)
  return (
    <>
      {/* Search — own full-width row so it always lays out cleanly */}
      <div className="mb-4 max-w-2xl"><PlayerSearch players={pickerPlayers} onPick={onPick} /></div>

      {/* Squad filter — wrapping chips */}
      {squads.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 mb-6">
          <span className="iq-eyebrow mr-0.5" style={{ fontSize: 9 }}>Squad</span>
          <SquadChip label="All squads" active={squad === ''} onClick={() => setSquad('')} />
          {squads.map(s => <SquadChip key={s.id} label={s.name} active={squad === s.id} onClick={() => setSquad(s.id)} />)}
        </div>
      )}

      {/* Selected squad's players — the visible response to the squad filter */}
      {squad !== '' && (
        <Card className="mb-9" eyebrow={`${pickerPlayers.length} player${pickerPlayers.length === 1 ? '' : 's'} · this season`} title={activeSquad?.name || 'Squad'}>
          {pickerPlayers.length === 0 ? <Empty>No current-season players in this squad.</Empty> : (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {pickerPlayers.map(p => (
                <button key={p.player_id} onClick={() => onPick(p.player_id)}
                  className="flex items-center gap-2.5 px-2.5 py-2 text-left transition" style={{ borderRadius: 10, background: 'var(--pb-surface2)', border: '1px solid var(--pb-hairline)' }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--pb-accent)' }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--pb-hairline)' }}>
                  <Initials name={p.name} size={32} />
                  <div className="min-w-0">
                    <div className="font-semibold text-[13px] truncate">{p.name}</div>
                    <div className="iq-mono text-pb-faintest text-[10.5px] truncate">{p.matches}g{p.runs ? ` · ${p.runs}r` : ''}{p.wickets ? ` · ${p.wickets}w` : ''}</div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </Card>
      )}

      {/* Form movers — surfaced first */}
      <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr] items-start mb-9">
        <Card eyebrow="this season vs career-before-it" title="Form movers">
          {m === null ? <div className="animate-pulse text-pb-faint text-sm">Loading…</div>
            : noMovers ? <Empty>Not enough multi-season history among current players to spot movers yet.</Empty>
              : (
                <div className="grid sm:grid-cols-2 gap-x-8 gap-y-5">
                  <MoverList title="Batting — rising" tone="up" items={m.batting?.risers} kind="bat" onPick={onPick} />
                  <MoverList title="Batting — sliding" tone="down" items={m.batting?.fallers} kind="bat" onPick={onPick} />
                  <MoverList title="Bowling — improving" tone="up" items={m.bowling?.risers} kind="bowl" onPick={onPick} />
                  <MoverList title="Bowling — slipping" tone="down" items={m.bowling?.fallers} kind="bowl" onPick={onPick} />
                </div>
              )}
          <Note>Deltas compare this season to each player's career average before it (min sample applies). Lower bowling average = improving.</Note>
        </Card>
        <Card eyebrow="ones to watch" title="Emerging">
          {!overview?.emerging?.length ? <Empty>No emerging players to flag yet.</Empty> : (
            <div className="space-y-3.5">
              {overview.emerging.map(e => (
                <button key={e.player_id} onClick={() => onPick(e.player_id)} className="flex gap-3 w-full text-left transition hover:opacity-80">
                  <Initials name={e.name} size={38} />
                  <div className="min-w-0">
                    <div className="font-semibold text-[14px] truncate">{e.name}</div>
                    <div className="text-pb-dim text-[12.5px] mt-0.5 leading-snug iq-num">{e.runs}r · {e.wickets}w · {e.seasons} season{e.seasons === 1 ? '' : 's'}</div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="text-pb-faint text-[13px]">Search a player above for their full trajectory, deep-dive and head-to-head compare.</div>
    </>
  )
}

/* ── Main ────────────────────────────────────────────────────────────────── */
export default function PlayerTrends() {
  const [searchParams, setSearchParams] = useSearchParams()
  const { ctx, seasons } = useIQFilter()
  const seasonId = ctx?.season?.to?.id || undefined
  const gradeId = ctx?.team?.id || undefined
  const [overview, setOverview] = useState(null)
  const [players, setPlayers] = useState([])
  const [squad, setSquad] = useState('')
  const playerId = searchParams.get('player') || null

  // Form movers, emerging and the player list all follow the global Season + Team
  // filter — re-fetch whenever it changes.
  useEffect(() => {
    setOverview(null)
    api.iqTrendsOverview(seasonId, gradeId).then(setOverview).catch(() => setOverview({ batting: {}, bowling: {}, emerging: [] }))
    api.iqTrendsPlayers(seasonId, gradeId).then(d => setPlayers(d || [])).catch(() => setPlayers([]))
  }, [seasonId, gradeId])

  const pick = (id) => setSearchParams({ player: id }, { replace: true })
  const clear = () => setSearchParams({}, { replace: true })

  const squads = useMemo(() => {
    const map = new Map()
    players.forEach(p => { if (p.squad_id) map.set(p.squad_id, p.squad_name) })
    return [...map.entries()].map(([id, name]) => ({ id, name })).sort((a, b) => (a.name || '').localeCompare(b.name || ''))
  }, [players])
  const pickerPlayers = useMemo(() => (squad ? players.filter(p => p.squad_id === squad) : players), [squad, players])

  return (
    <IQLayout title="Player trends" actions={playerId ? <Btn variant="ghost" sm icon="back" onClick={clear}>All players</Btn> : null}>
      {playerId ? (
        <PlayerDetail playerId={playerId} players={players} ctx={ctx} seasons={seasons} onClear={clear} />
      ) : (
        <>
          <PageIntro>Who's rising, who's sliding, and the full statistical picture on any player — surfaced up front, not buried.</PageIntro>
          <Overview overview={overview} players={players} squads={squads} squad={squad} setSquad={setSquad} pickerPlayers={pickerPlayers} onPick={pick} />
        </>
      )}
    </IQLayout>
  )
}
