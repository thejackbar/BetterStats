/* BetterIQ — Team analysis: the opposition lens, pointed at us.
   Reads the GLOBAL Season + Team filter (useIQFilter). Single-season pulls one
   overview; a season RANGE additionally plots win-rate-over-time across the
   in-range seasons. Every section is guarded — any sub-object may be null. */
import { useState, useEffect } from 'react'
import IQLayout from '../../../components/admin/IQLayout'
import { api } from '../../../lib/api'
import {
  Icon, Card, Stat, Note, Tag, Bar, Gauge, SplitBar, StackedBar,
  Initials, KV, Empty, Tabs, PageIntro, Delta, a2,
} from './ui'
import { AreaChart, PhaseStrip } from './viz'
import { useIQFilter, seasonsInRange } from './Context'

const TABS = [
  { value: 'overview', label: 'Overview' },
  { value: 'batting', label: 'Batting' },
  { value: 'bowling', label: 'Bowling' },
  { value: 'players', label: 'Players' },
]

const ord = (k) => ({ 1: '1st', 2: '2nd', 3: '3rd' }[k] || `${k}th`)
const pctTxt = (v) => (v === null || v === undefined ? '—' : `${v}%`)
const num = (v, dash = '—') => (v === null || v === undefined ? dash : v)
const bandColor = (v) => (v >= 70 ? 'var(--pb-brand)' : v >= 45 ? 'var(--pb-amber)' : 'var(--pb-red)')

/* ── How we win / lose — bullet list with up/down glyphs ─────────────────── */
function WinLoseList({ items, tone }) {
  if (!items?.length) return <Empty>Not enough games to read a pattern yet.</Empty>
  const color = tone === 'win' ? 'var(--pb-brand)' : 'var(--pb-red)'
  const glyph = tone === 'win' ? '▲' : '▼'
  return (
    <ul className="space-y-2.5">
      {items.map((b, i) => (
        <li key={i} className="flex gap-2.5 text-[13.5px] leading-snug">
          <span style={{ color }} className="shrink-0">{glyph}</span>
          <span>{b}</span>
        </li>
      ))}
    </ul>
  )
}

/* ── Win rate over time (range mode only) ───────────────────────────────── */
function SeasonCompare({ rows, loading }) {
  if (loading) {
    return <div className="iq-card p-6 animate-pulse text-pb-faint text-sm">Comparing seasons…</div>
  }
  const usable = (rows || []).filter(r => r.win_pct !== null && r.win_pct !== undefined)
  if (usable.length < 2) return null
  const first = usable[0].win_pct, last = usable[usable.length - 1].win_pct
  return (
    <Card accent eyebrow={`comparing ${usable.length} seasons`} title="Win rate over time"
      right={<Delta value={last - first} suffix=" pts" />}>
      <AreaChart points={usable.map(r => r.win_pct)} labels={usable.map(r => r.label)} format={v => `${v}%`} />
      <Note>Win % per season across the selected range — record shown is over all games that season.</Note>
    </Card>
  )
}

/* ── Overview tab ───────────────────────────────────────────────────────── */
function Overview({ d, isRange, compareRows, compareLoading }) {
  const r = d.record
  const inn = d.innings
  return (
    <div className="space-y-5">
      {isRange && <SeasonCompare rows={compareRows} loading={compareLoading} />}

      {/* record + how we win/lose */}
      <div className="grid gap-5 lg:grid-cols-[auto_1fr] items-stretch">
        <Card className="flex items-center justify-center">
          <div className="flex flex-col items-center px-4 py-1">
            {r.win_pct === null || r.win_pct === undefined
              ? <Stat label="Win rate" value="—" />
              : <Gauge value={r.win_pct} size={130} label="Win rate" />}
            <div className="iq-num text-pb-faint text-[12.5px] mt-2">
              {r.wins}–{r.losses}{r.draws ? `–${r.draws}` : ''} from {r.matches}
            </div>
            <div className="flex gap-2 mt-3">
              <Tag tone="faint">H {r.home?.wins ?? 0}/{r.home?.played ?? 0}</Tag>
              <Tag tone="faint">A {r.away?.wins ?? 0}/{r.away?.played ?? 0}</Tag>
            </div>
          </div>
        </Card>
        <div className="grid gap-5 sm:grid-cols-2">
          <Card eyebrow="patterns" title="How we win"><WinLoseList items={d.how_we_win} tone="win" /></Card>
          <Card eyebrow="patterns" title="How we lose"><WinLoseList items={d.how_we_lose} tone="loss" /></Card>
        </div>
      </div>

      {/* bat first vs chase + par/score bands */}
      <div className="grid gap-5 lg:grid-cols-2 items-start">
        {inn && (
          <Card eyebrow="approach" title="Bat first vs chase">
            <div className="grid grid-cols-2 gap-5 mb-4">
              <div>
                <div className="iq-headline iq-num" style={{ fontSize: 30, color: 'var(--pb-brand)' }}>{pctTxt(inn.bat_first?.win_pct)}</div>
                <div className="iq-eyebrow mt-1.5">Batting first</div>
                <div className="text-pb-faint text-[11px] mt-1 iq-num">{inn.bat_first?.wins ?? 0}/{inn.bat_first?.played ?? 0} · avg {num(inn.bat_first?.avg_score)}</div>
              </div>
              <div>
                <div className="iq-headline iq-num" style={{ fontSize: 30, color: 'var(--pb-amber)' }}>{pctTxt(inn.chasing?.win_pct)}</div>
                <div className="iq-eyebrow mt-1.5">Chasing</div>
                <div className="text-pb-faint text-[11px] mt-1 iq-num">{inn.chasing?.wins ?? 0}/{inn.chasing?.played ?? 0} · avg target {num(inn.chasing?.avg_target)}</div>
              </div>
            </div>
            <Note>Win % over decided games for each first-innings choice.</Note>
          </Card>
        )}

        {d.score_bands?.length > 0 && (
          <Card eyebrow="what score wins" title={inn?.par?.par_score != null ? `Par: ${inn.par.par_score}` : 'What score wins'}
            right={inn?.par?.lowest_defended != null ? <span className="text-pb-faint text-[12px] iq-num">defended {inn.par.lowest_defended}</span> : null}>
            <div className="space-y-2.5">
              {d.score_bands.map((s, i) => (
                <div key={s.band} className="flex items-center gap-3 text-[13px]">
                  <span className="iq-mono text-pb-faint w-16 shrink-0">{s.band}</span>
                  <div className="flex-1"><Bar pct={s.win_pct || 0} color={bandColor(s.win_pct || 0)} delay={i * 0.06} h={10} /></div>
                  <span className="iq-num w-16 text-right font-semibold shrink-0">{pctTxt(s.win_pct)} <span className="text-pb-faintest">({s.played})</span></span>
                </div>
              ))}
            </div>
            <Note>Win rate when we post a first-innings total in each band (count of such games in brackets).</Note>
          </Card>
        )}
      </div>

      {/* by venue */}
      {d.venues?.length > 0 && (
        <Card eyebrow="home vs away" title="By venue">
          <div className="grid sm:grid-cols-2 gap-x-6 gap-y-4">
            {d.venues.map(v => {
              const winning = v.wins > v.losses
              return (
                <div key={v.venue}>
                  <div className="flex items-center justify-between mb-1.5 gap-2">
                    <span className="text-[13.5px] truncate">{v.venue}</span>
                    <span className="iq-num text-[13px] whitespace-nowrap" style={{ color: winning ? 'var(--pb-brand)' : 'var(--pb-red)' }}>
                      {v.wins}–{v.losses}<span className="text-pb-faintest">/{v.played}</span>
                    </span>
                  </div>
                  <Bar pct={v.played ? (v.wins / v.played) * 100 : 0} color={winning ? 'var(--pb-brand)' : 'var(--pb-red)'} h={7} />
                  {v.avg_score != null && <div className="text-pb-faintest text-[11px] mt-1 iq-num">avg score {v.avg_score}</div>}
                </div>
              )
            })}
          </div>
        </Card>
      )}
    </div>
  )
}

/* ── Batting tab ────────────────────────────────────────────────────────── */
function Batting({ d, seasonId, teamId }) {
  const b = d.batting || {}
  const starts = d.starts
  const maxP = Math.max(1, ...((d.partnerships || []).map(p => p.avg_partnership || 0)))
  const c = d.collapses
  const be = d.batting_extra
  const dist = b.total_distribution || []
  const maxRuns = Math.max(1, ...((be?.top_scorers || []).map(s => s.runs || 0)))

  return (
    <div className="space-y-5">
      <TeamPhases seasonId={seasonId} teamId={teamId} side="bat" />
      <div className="grid gap-5 lg:grid-cols-3">
        <Card eyebrow="profile" title="Team batting">
          <div className="space-y-1">
            <Stat label="Avg score" value={num(b.avg_score)} count={false} />
            <div className="pt-2 mt-2" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
              <KV label="High score" value={num(b.high_score)} />
              <KV label="Low score" value={num(b.low_score)} />
              <KV label="Wkts lost / inns" value={num(b.avg_wickets_lost)} />
              <KV label="Boundary %" value={pctTxt(b.boundary_pct)} />
            </div>
          </div>
          {b.top_order_pct != null && (
            <div className="mt-4">
              <div className="iq-eyebrow mb-1.5">Where our runs come from</div>
              <SplitBar h={12} segments={[
                { label: `Top 3 ${b.top_order_pct}%`, value: b.top_order_pct, color: 'var(--pb-accent)' },
                { label: `Middle ${b.middle_pct}%`, value: b.middle_pct, color: 'var(--pb-amber)' },
                { label: `Lower ${b.lower_pct}%`, value: b.lower_pct, color: 'var(--pb-dim)' },
              ]} />
              <div className="flex justify-between text-[11px] text-pb-faint mt-1.5 iq-num">
                <span>Top 3 {b.top_order_pct}%</span><span>Mid {b.middle_pct}%</span><span>Lower {b.lower_pct}%</span>
              </div>
            </div>
          )}
        </Card>

        {starts ? (
          <Card eyebrow="opening stand" title="Our starts">
            <div className="grid grid-cols-2 gap-3">
              <Stat label="Avg" value={num(starts.avg)} count={false} />
              <Stat label="Best" value={num(starts.best)} count={false} />
            </div>
            <div className="pt-3 mt-3" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
              <KV label="Median" value={num(starts.median)} />
              <KV label="25+ / 50+" value={`${starts.over_25 ?? 0} / ${starts.over_50 ?? 0}`} />
              {starts.after_good && <KV label={`After good (≥${starts.good_threshold})`} value={`${pctTxt(starts.after_good.win_pct)} · ${starts.after_good.played}g`} tone="win" />}
              {starts.after_poor && <KV label={`After poor (<${starts.good_threshold})`} value={`${pctTxt(starts.after_poor.win_pct)} · ${starts.after_poor.played}g`} tone="loss" />}
            </div>
            <Note>Opening (1st-wicket) partnership; win rate is over decided games.</Note>
          </Card>
        ) : (
          <Card eyebrow="opening stand" title="Our starts"><Empty>No opening-stand data.</Empty></Card>
        )}

        <Card eyebrow="partnerships" title="Avg by wicket">
          {d.partnerships?.length > 0 ? (
            <div className="space-y-1.5">
              {d.partnerships.map((p, i) => (
                <div key={p.wicket} className="flex items-center gap-2 text-[12px]">
                  <span className="iq-mono text-pb-faint w-7 shrink-0">{ord(p.wicket)}</span>
                  <div className="flex-1"><Bar pct={(p.avg_partnership / maxP) * 100} delay={i * 0.05} h={7} /></div>
                  <span className="iq-num w-9 text-right shrink-0">{p.avg_partnership}</span>
                </div>
              ))}
            </div>
          ) : <Empty>No partnership data.</Empty>}
        </Card>
      </div>

      <div className="grid gap-5 lg:grid-cols-2 items-start">
        {d.batting_pairs?.length > 0 && (
          <Card eyebrow="our most productive" title="Best partnership pairs">
            <div className="space-y-2.5">
              {d.batting_pairs.map((p, i) => (
                <div key={i} className="flex items-center justify-between gap-3 text-[13.5px]">
                  <div className="min-w-0 flex items-baseline gap-2">
                    <span className="font-semibold truncate">{p.a} &amp; {p.b}</span>
                    {p.opening && <Tag tone="faint">opening</Tag>}
                  </div>
                  <div className="flex items-center gap-3 whitespace-nowrap text-pb-faint iq-num text-[12.5px]">
                    <span>{p.stands} stands</span>
                    <span className="font-semibold text-pb-text">{p.runs} @ {a2(p.avg)}</span>
                    <span className="w-20 text-right">best {p.best}{p.fifties ? ` · ${p.fifties}×50` : ''}</span>
                  </div>
                </div>
              ))}
            </div>
            <Note>Average is runs per stand together (not a batting average).</Note>
          </Card>
        )}

        {c && c.innings_analysed > 0 && (
          <Card accent eyebrow="the recurring wobble" title="Collapse analysis"
            right={<span className="text-pb-faint text-[12px]">3 wkts ≤{c.threshold}</span>}>
            <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
              <div>
                <span className="iq-headline iq-num" style={{ fontSize: 28 }}>{pctTxt(c.collapse_pct)}</span>
                <span className="text-pb-faint text-[13px] ml-2">of innings ({c.collapse_count}/{c.innings_analysed})</span>
              </div>
              {c.worst && <div className="text-[13px] text-pb-faint">Worst: <span className="iq-num font-semibold text-pb-text">3 for {c.worst.runs}</span> from the {ord(c.worst.start_wicket)}</div>}
            </div>
            {c.by_start_wicket?.length > 0 && (
              <div className="mt-4 pt-4" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
                <div className="iq-eyebrow mb-2">Where the wheels come off</div>
                <div className="flex flex-wrap gap-2">
                  {c.by_start_wicket.map(w => (
                    <span key={w.wicket} className="text-[12px] px-2 py-1 rounded-lg iq-num" style={{ background: 'var(--pb-surface2)' }}>{ord(w.wicket)} wkt ×{w.count}</span>
                  ))}
                </div>
              </div>
            )}
            <Note>A collapse = losing any 3 wickets in a row for ≤{c.threshold} runs, reconstructed from stored partnerships.</Note>
          </Card>
        )}
      </div>

      {/* extra batting graphs (brief §1/§7) — total distribution, scorers,
          by-position, dismissals, dismissal-score histogram */}
      {(dist.length > 0 || be?.dismissal_scores?.length > 0) && (
        <div className="grid gap-5 lg:grid-cols-2 items-start">
          {dist.length > 0 && (
            <Card eyebrow="how big do we bat" title="Team total distribution">
              <MiniBars data={dist} fmt={x => `${x.pct}%`} />
              <Note>Share of the innings we have a total for that finished in each score band.</Note>
            </Card>
          )}
          {be?.dismissal_scores?.length > 0 && (
            <Card eyebrow="when we fall" title="Score we're dismissed on">
              <MiniBars data={be.dismissal_scores} color="var(--pb-red)" fmt={x => `${x.pct}%`} />
              <Note>What score our batters are usually on when out — too many cheap dismissals shows in the low bands.</Note>
            </Card>
          )}
        </div>
      )}

      {be && (be.top_scorers?.length > 0 || be.by_position?.length > 0) && (
        <div className="grid gap-5 lg:grid-cols-2 items-start">
          {be.top_scorers?.length > 0 && (
            <Card eyebrow="run-makers" title="Leading scorers">
              <div className="space-y-3">
                {be.top_scorers.map((s, i) => (
                  <div key={s.player_id} className="flex items-center gap-3">
                    <Initials name={s.name} size={30} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold text-[13.5px] truncate">{s.name}</span>
                        <span className="iq-num text-pb-faint text-[12px] whitespace-nowrap">{s.runs} runs · {s.innings} inns{s.avg != null ? ` · ${a2(s.avg)}` : ''}</span>
                      </div>
                      <Bar pct={(s.runs / maxRuns) * 100} delay={i * 0.05} h={6} />
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}
          {be.by_position?.length > 0 && (
            <Card eyebrow="down the order" title="Average by batting position">
              <MiniBars data={be.by_position} labelKey="position" valueKey="avg" fmt={x => a2(x.avg)} />
              <Note>Average runs per innings at each position we've batted (1–11).</Note>
            </Card>
          )}
        </div>
      )}

      {be?.dismissals?.length > 0 && (
        <Card eyebrow="how we get out" title="Our dismissal types">
          <StackedBar data={be.dismissals.map(x => ({ type: x.type, count: x.pct, pct: x.pct }))} />
          <Note>How our batters are dismissed across the period — a high caught share with cheap scores points to shot selection.</Note>
        </Card>
      )}
    </div>
  )
}

/* ── Innings phases (estimated, from ball-by-ball games) ──────────────────── */
/* Only recent live-scored games carry ball-by-ball data; older games are
   scorecard-only. The endpoint reports `available:false` when there's nothing
   to break down, in which case we render nothing. */
function TeamPhases({ seasonId, teamId, side = 'bat' }) {
  const [ph, setPh] = useState(null)
  useEffect(() => {
    setPh(null)
    let alive = true
    api.iqTeamPhases(seasonId || undefined, teamId || undefined, side)
      .then(d => { if (alive) setPh(d) })
      .catch(() => { if (alive) setPh(null) })
    return () => { alive = false }
  }, [seasonId, teamId, side])
  if (!ph?.available) return null
  const title = side === 'bowl' ? 'Innings phases — what we concede' : 'Innings phases — how we bat'
  return (
    <Card eyebrow="Estimated · ball-by-ball" title={title}
      right={ph.innings ? <Tag tone="faint">{ph.innings}{ph.total != null ? ` · ${ph.total}` : ''}</Tag> : null}>
      <PhaseStrip phases={ph.phases} />
      {ph.insight && <div className="text-pb-dim text-[12.5px] mt-4 leading-relaxed">{ph.insight}</div>}
      {ph.note && <Note>{side === 'bowl' ? 'Runs the opposition scored against us by phase, from ' : 'Our scoring shape by phase, from '}{ph.note.replace(/^Estimated from /, '')}</Note>}
    </Card>
  )
}

/* ── A simple labelled vertical bar histogram (10-run bands etc.) ─────────── */
function MiniBars({ data, color = 'var(--pb-accent)', valueKey = 'count', labelKey = 'band', fmt }) {
  const max = Math.max(1, ...data.map(d => d[valueKey] || 0))
  return (
    <div className="flex items-end gap-1.5" style={{ height: 120 }}>
      {data.map((d, i) => (
        <div key={d[labelKey] ?? i} className="flex-1 flex flex-col items-center justify-end h-full" title={`${d[labelKey]}: ${fmt ? fmt(d) : d[valueKey]}`}>
          <span className="iq-num text-[10.5px] mb-1" style={{ color: 'var(--pb-faint)' }}>{fmt ? fmt(d) : d[valueKey]}</span>
          <div className="w-full" style={{ height: `${((d[valueKey] || 0) / max) * 100}%`, minHeight: d[valueKey] ? 3 : 0, background: color, borderRadius: '4px 4px 0 0', transformOrigin: 'bottom', animation: `iq-grow .8s cubic-bezier(.22,.61,.36,1) ${i * 0.04}s both` }} />
          <span className="iq-mono text-[9.5px] mt-1.5 text-center" style={{ color: 'var(--pb-faint)' }}>{d[labelKey]}</span>
        </div>
      ))}
    </div>
  )
}

/* ── Bowling tab ────────────────────────────────────────────────────────── */
function Bowling({ d, seasonId, teamId }) {
  const bw = d.bowling || {}
  const attack = d.attack
  const disc = d.discipline
  const wq = d.wickets_quality
  const maxShare = Math.max(1, ...((attack?.bowlers || []).map(a => a.wickets || 0)))

  return (
    <div className="space-y-5">
      <TeamPhases seasonId={seasonId} teamId={teamId} side="bowl" />
      <Card eyebrow="summary" title="Attack overall">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <Stat label="Avg conceded" value={num(bw.avg_conceded)} count={false} />
          <Stat label="Wkts / game" value={num(bw.avg_wickets_taken)} count={false} />
          {attack && <Stat label="Pace" value={pctTxt(attack.pace_pct)} tone="accent" count={false} />}
          {attack && <Stat label="Spin" value={pctTxt(attack.spin_pct)} count={false} />}
        </div>
        <Note>We concede {num(bw.avg_conceded)} on average per innings; wickets per game is across all completed games.</Note>
      </Card>

      {attack && attack.bowlers?.length > 0 && (
        <Card eyebrow="who does what" title="Attack structure"
          right={<span className="text-pb-faint text-[12px] iq-num">{attack.pace_pct}% pace · {attack.spin_pct}% spin</span>}>
          <div className="space-y-3">
            {attack.bowlers.map((a, i) => (
              <div key={a.player_id} className="flex items-center gap-3">
                <Initials name={a.name} size={34} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-[14px] truncate">{a.name}</span>
                    <span className="iq-num text-pb-faint text-[12px] whitespace-nowrap">{a.wickets}w · avg {a2(a.avg)} · econ {a2(a.econ)}</span>
                  </div>
                  <div className="text-pb-faint text-[11.5px] mb-1">{a.role}{a.spin ? ' · spin' : a.pace ? ' · pace' : ''} · {a.overs} ov</div>
                  <Bar pct={(a.wickets / maxShare) * 100} delay={i * 0.06} h={6} />
                </div>
              </div>
            ))}
          </div>
          <Note><b>Strike</b> takes wickets quickly · <b>Containment</b> restricts runs · <b>Stock</b> workhorse. Frontline bowlers only; bar = share of wickets.</Note>
        </Card>
      )}

      {disc && (
        <Card eyebrow="discipline" title="Extras conceded"
          right={<span className="text-pb-faint text-[12px] iq-num">{pctTxt(disc.extras_pct)} of runs</span>}>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-1">
            <Stat label="Extras / over" value={num(disc.extras_per_over)} count={false} />
            <Stat label="Wides / over" value={num(disc.wides_per_over)} count={false} />
            <Stat label="Total extras" value={num(disc.extras)} sub={`${disc.wides ?? 0}w · ${disc.no_balls ?? 0}nb`} count={false} />
            <Stat label="% of runs" value={pctTxt(disc.extras_pct)} sub="conceded" count={false} />
          </div>
          {disc.bowlers?.length > 0 && (
            <div className="mt-2 space-y-1.5">
              {disc.bowlers.map(bl => (
                <div key={bl.player_id} className="flex items-center justify-between gap-3 text-[12.5px] py-0.5">
                  <span className="font-medium truncate">{bl.name}</span>
                  <span className="iq-num text-pb-faint whitespace-nowrap">{bl.overs} ov · {bl.wides}w · {bl.no_balls}nb · <span className="font-semibold text-pb-text">{num(bl.extras_per_over)}/ov</span></span>
                </div>
              ))}
            </div>
          )}
          <Note>Wides + no-balls per over, <b>worst offenders first</b> so they can be identified and coached. Hidden when the scorecards don't record extras.</Note>
        </Card>
      )}

      {wq && (
        <Card eyebrow="wicket-taking" title="Quality of our wickets"
          right={<span className="text-pb-faint text-[12px] iq-num">{num(wq.total)} wkts</span>}>
          {wq.top_pct != null && (
            <div className="mb-4">
              <div className="iq-eyebrow mb-1.5">Which batters we remove</div>
              <SplitBar h={12} segments={[
                { label: `Top order ${wq.top}`, value: wq.top, color: 'var(--pb-accent)' },
                { label: `Middle ${wq.middle}`, value: wq.middle, color: 'var(--pb-amber)' },
                { label: `Tail ${wq.tail}`, value: wq.tail, color: 'var(--pb-dim)' },
              ]} />
              <div className="flex justify-between text-[11px] text-pb-faint mt-1.5 iq-num">
                <span>Top {wq.top_pct}%</span><span>Middle</span><span>Tail {wq.tail_pct}%</span>
              </div>
            </div>
          )}
          <div className="grid grid-cols-3 gap-3">
            <Stat label="Set (30+)" value={pctTxt(wq.set_pct)} sub="of scalps" count={false} />
            <Stat label="New (<10)" value={pctTxt(wq.new_pct)} sub="of scalps" count={false} />
            <Stat label="Wickets" value={num(wq.total)} count={false} />
          </div>
          {wq.score_bands?.length > 0 && (
            <div className="mt-4 pt-4" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
              <div className="iq-eyebrow mb-2.5">What score we remove them on</div>
              <MiniBars data={wq.score_bands} fmt={x => `${x.pct}%`} />
              <Note>The score the opposition batter was on when our bowlers dismissed them (10-run bands) — lots in the low bands means we strike early.</Note>
            </div>
          )}
          {wq.dismissals?.length > 0 && (
            <div className="mt-4 pt-4" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
              <div className="iq-eyebrow mb-2.5">How we take them</div>
              <StackedBar data={wq.dismissals.map(x => ({ type: x.type, count: x.pct, pct: x.pct }))} />
            </div>
          )}
          <Note>From wickets credited to our bowlers; “set” = the batter had 30+ when out, “new” = under 10.</Note>
        </Card>
      )}
    </div>
  )
}

/* ── Players tab ────────────────────────────────────────────────────────── */
function Players({ d }) {
  const cap = d.captaincy
  const roles = d.role_ratings
  const ar = d.all_rounders
  const fld = d.fielding
  const maxRating = Math.max(1, ...((ar || []).map(a => Math.abs(a.diff || 0))))
  const nothing = !cap?.length && !roles?.length && !ar?.length && !(fld?.fielders?.length || fld?.keepers?.length)

  if (nothing) return <Card><Empty>Not enough per-player data in this period.</Empty></Card>

  return (
    <div className="space-y-5">
      {cap?.length > 0 && (
        <Card eyebrow="leadership" title="Captaincy" right={<span className="text-pb-faint text-[12px]">record as skipper</span>}>
          <div className="space-y-3">
            {cap.map(c => (
              <div key={c.player_id} className="flex items-center gap-3">
                <Initials name={c.name} size={34} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="font-semibold text-[14px] truncate">{c.name}</span>
                    <span className="iq-num font-bold text-[14px]" style={{ color: c.win_pct != null && c.win_pct >= 50 ? 'var(--pb-brand)' : 'var(--pb-text)' }}>{pctTxt(c.win_pct)}</span>
                  </div>
                  <div className="text-pb-faint text-[12px] mt-0.5 iq-num">
                    {c.wins}–{c.losses}–{c.draws} from {c.led} · avg {num(c.avg_score)}{c.finals ? ` · finals ${c.finals_won}/${c.finals}` : ''}
                  </div>
                </div>
              </div>
            ))}
          </div>
          <Note>Win % over decided games (draws excluded); avg score is our total in games they led. Min 3 games. Toss decisions aren't in our data.</Note>
        </Card>
      )}

      <div className="grid gap-5 lg:grid-cols-2 items-start">
        {ar?.length > 0 && (
          <Card eyebrow="role-adjusted" title="All-rounders" right={<span className="text-pb-faint text-[12px]">bat − bowl avg</span>}>
            <div className="space-y-3">
              {ar.map((a, i) => (
                <div key={a.player_id} className="flex items-center gap-3">
                  <Initials name={a.name} size={32} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-semibold text-[13.5px] truncate">{a.name}</span>
                      {a.diff != null && <span className="iq-num font-bold text-[13px]" style={{ color: a.diff >= 0 ? 'var(--pb-brand)' : 'var(--pb-amber)' }}>{a.diff >= 0 ? '+' : ''}{a2(a.diff)}</span>}
                    </div>
                    <div className="text-pb-faint text-[11.5px] mb-1 iq-num">{a.runs} @ {a2(a.bat_avg)} · {a.wickets}w @ {a2(a.bowl_avg)} · {a.role}</div>
                    <Bar pct={(Math.abs(a.diff || 0) / maxRating) * 100} delay={i * 0.06} h={5} color={a.diff >= 0 ? 'var(--pb-accent)' : 'var(--pb-amber)'} />
                  </div>
                </div>
              ))}
            </div>
            <Note>Ranked by batting average − bowling average; a positive figure leans batting.</Note>
          </Card>
        )}

        {roles?.length > 0 && (
          <Card eyebrow="role-adjusted batting" title="Vs same-slot average">
            <div className="space-y-2.5">
              {roles.map(rr => (
                <div key={rr.player_id} className="flex items-center justify-between gap-3 text-[13px]">
                  <div className="min-w-0">
                    <span className="font-semibold truncate">{rr.name}</span>
                    <span className="text-pb-faint text-[11px] ml-2">{rr.role} · {rr.innings} inns</span>
                  </div>
                  <div className="flex items-center gap-3 whitespace-nowrap iq-num text-pb-faint text-[12.5px]">
                    <span>{a2(rr.average)} <span className="text-pb-faintest">vs {a2(rr.role_average)}</span></span>
                    <span className="font-semibold w-14 text-right" style={{ color: rr.delta >= 0 ? 'var(--pb-brand)' : 'var(--pb-red)' }}>{rr.delta >= 0 ? '+' : ''}{a2(rr.delta)}</span>
                  </div>
                </div>
              ))}
            </div>
            <Note>Each batter's average in their main position vs the club average for that slot — so an opener and a No. 8 aren't judged alike.</Note>
          </Card>
        )}
      </div>

      {fld && (fld.fielders?.length > 0 || fld.keepers?.length > 0) && (
        <div className="grid gap-5 lg:grid-cols-2 items-start">
          <Card eyebrow="in the field" title="Top fielders">
            {fld.fielders?.length ? (
              <div className="space-y-1.5">
                {fld.fielders.map(f => (
                  <div key={f.player_id} className="flex justify-between gap-2 text-[13.5px] py-0.5">
                    <span className="truncate">{f.name}</span>
                    <span className="iq-num text-pb-faint whitespace-nowrap">{f.catches}c{f.run_outs ? ` · ${f.run_outs} ro` : ''}</span>
                  </div>
                ))}
              </div>
            ) : <Empty>—</Empty>}
            {fld.combos?.length > 0 && (
              <div className="mt-3 pt-3" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
                <div className="iq-eyebrow mb-1.5">Catching combos</div>
                {fld.combos.slice(0, 5).map((c, i) => (
                  <div key={i} className="text-[12px] text-pb-faint py-0.5 iq-num">{c.fielder} off {c.bowler} ×{c.count}</div>
                ))}
              </div>
            )}
          </Card>
          <Card eyebrow="behind the stumps" title="Wicketkeepers">
            {fld.keepers?.length ? (
              <div className="space-y-1.5">
                {fld.keepers.map(k => (
                  <div key={k.player_id} className="flex justify-between gap-2 text-[13.5px] py-0.5">
                    <span className="truncate">{k.name}</span>
                    <span className="iq-num text-pb-faint whitespace-nowrap">{k.catches}c · {k.stumpings}st</span>
                  </div>
                ))}
              </div>
            ) : <Empty>No keeper data.</Empty>}
          </Card>
        </div>
      )}
    </div>
  )
}

/* ── Page ───────────────────────────────────────────────────────────────── */
export default function TeamAnalysis() {
  const { ctx, seasons } = useIQFilter()
  const [tab, setTab] = useState('overview')
  const [data, setData] = useState(null)
  const [err, setErr] = useState(false)

  // win-rate-over-time (range mode only)
  const [compareRows, setCompareRows] = useState([])
  const [compareLoading, setCompareLoading] = useState(false)

  const seasonId = ctx?.season?.to?.id || null
  const teamId = ctx?.team?.id || null
  const isRange = ctx?.season?.mode === 'range'

  // Single-season / headline overview (always for the chosen "to" season).
  useEffect(() => {
    if (!ctx) return
    let alive = true
    setData(null); setErr(false)
    api.iqTeamOverview(seasonId || undefined, teamId || undefined)
      .then(d => { if (alive) setData(d) })
      .catch(() => { if (alive) setErr(true) })
    return () => { alive = false }
  }, [ctx, seasonId, teamId])

  // Win-rate-over-time across the in-range seasons (range mode only).
  useEffect(() => {
    if (!ctx || !isRange) { setCompareRows([]); setCompareLoading(false); return }
    const inRange = seasonsInRange(ctx, seasons)
    if (inRange.length < 2) { setCompareRows([]); setCompareLoading(false); return }
    let alive = true
    setCompareLoading(true)
    Promise.all(inRange.map(s =>
      api.iqTeamOverview(s.id, teamId || undefined)
        .then(d => ({ label: s.label, win_pct: d?.record?.win_pct ?? null }))
        .catch(() => ({ label: s.label, win_pct: null }))
    )).then(rows => {
      if (!alive) return
      setCompareRows(rows)
      setCompareLoading(false)
    })
    return () => { alive = false }
    // key on the concrete range + team so a filter change cancels the stale fetch
  }, [ctx, isRange, teamId, seasonsInRange(ctx, seasons).map(s => s.id).join(',')])

  const ready = !!ctx

  return (
    <IQLayout title="Team analysis">
      <PageIntro>The opposition lens, pointed at us — how we win and lose, our batting & bowling shape, and where we're strong or fragile. Use the filter above to focus a season or compare across years.</PageIntro>

      {!ready && <div className="iq-card p-6 animate-pulse text-pb-faint text-sm">Loading…</div>}

      {ready && (
        <>
          <div className="mb-6"><Tabs value={tab} onChange={setTab} tabs={TABS} /></div>

          {data === null && !err && <div className="iq-card p-6 animate-pulse text-pb-faint text-sm">Crunching our games…</div>}
          {err && <div className="iq-card p-6"><Empty>Couldn't load team analysis.</Empty></div>}

          {data && data.record && (
            <div className="iq-fade">
              {tab === 'overview' && <Overview d={data} isRange={isRange} compareRows={compareRows} compareLoading={compareLoading} />}
              {tab === 'batting' && <Batting d={data} seasonId={seasonId} teamId={teamId} />}
              {tab === 'bowling' && <Bowling d={data} seasonId={seasonId} teamId={teamId} />}
              {tab === 'players' && <Players d={data} />}

              {data.coverage?.notes?.length > 0 && (
                <div className="text-pb-faintest text-[11px] mt-6 flex items-start gap-1.5">
                  <Icon name="info" size={13} className="mt-0.5 shrink-0" />
                  <span>{data.coverage.notes.join(' ')}</span>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </IQLayout>
  )
}
