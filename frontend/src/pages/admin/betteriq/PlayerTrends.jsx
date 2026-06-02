import { useState, useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import IQLayout from '../../../components/admin/IQLayout'
import { api } from '../../../lib/api'
import { Icon, Btn, Tag, Empty, Search } from '../betterselect/ui'

const num = (v, dash = '—') => (v === null || v === undefined ? dash : v)
const TYPE_LABEL = { runs: 'runs', wickets: 'wickets', matches: 'games', catches: 'catches' }

function Card({ title, right, children, accent = false }) {
  return (
    <div className="pb-card p-4 md:p-5" style={accent ? { borderColor: 'color-mix(in srgb, var(--pb-accent) 30%, transparent)' } : undefined}>
      {(title || right) && (
        <div className="flex items-center justify-between gap-3 mb-3">
          <h3 className="font-display font-bold">{title}</h3>
          {right}
        </div>
      )}
      {children}
    </div>
  )
}

function VerdictTag({ v }) {
  if (!v) return null
  const map = { rising: ['Rising', 'var(--pb-brand)'], declining: ['Declining', 'var(--pb-red)'], steady: ['Steady', 'var(--pb-faint)'] }
  const [label, color] = map[v] || []
  if (!label) return null
  return <span className="font-mono text-[10px] px-1.5 py-0.5 rounded" style={{ background: `color-mix(in srgb, ${color} 16%, transparent)`, color }}>{label}</span>
}

/* ── overview: milestones + movers ────────────────────────────────────────── */

function fmtEta(g) { return g ? `~${g} game${g === 1 ? '' : 's'}` : null }

function Sparkline({ values, max }) {
  if (!values?.length) return <span className="text-pb-faintest text-[11px]">—</span>
  const m = max || Math.max(1, ...values)
  return (
    <span className="inline-flex items-end gap-[2px] h-5">
      {values.map((v, i) => (
        <span key={i} title={String(v)} className="w-[5px] rounded-sm"
          style={{ height: `${Math.max(8, Math.round((v / m) * 100))}%`, background: 'color-mix(in srgb, var(--pb-accent) 70%, transparent)' }} />
      ))}
    </span>
  )
}

function MilestoneList({ items }) {
  if (!items?.length) return <Empty>No milestones in reach right now.</Empty>
  return (
    <div className="space-y-2">
      {items.map((m, i) => (
        <div key={i} className="flex items-center justify-between gap-2">
          <span className="font-medium truncate">{m.name}</span>
          <span className="text-sm pb-num whitespace-nowrap">
            <b>{m.needed}</b> <span className="text-pb-faint">more {TYPE_LABEL[m.type] || m.type} → {m.target}{m.eta_games ? ` · ${fmtEta(m.eta_games)}` : ''}</span>
          </span>
        </div>
      ))}
    </div>
  )
}

function Movers({ title, rows, kind, onPick }) {
  if (!rows?.length) return null
  const isBat = kind === 'bat'
  return (
    <div>
      <div className="text-pb-faint text-[11px] uppercase tracking-wide2 mb-2">{title}</div>
      <div className="space-y-1.5">
        {rows.map(p => (
          <button key={p.player_id} onClick={() => onPick(p.player_id)} className="w-full flex items-center justify-between gap-2 text-left hover:text-pb-accent transition-colors">
            <span className="font-medium truncate">{p.name} <span className="text-pb-faintest text-[11px]">'{String(p.latest_year).slice(-2)}</span></span>
            <span className="text-sm pb-num whitespace-nowrap text-pb-faint">
              {isBat ? 'avg' : 'avg'} {p.baseline} <span style={{ color: 'var(--pb-accent)' }}>→ {p.latest}</span>
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}

/* ── player detail: trajectory ────────────────────────────────────────────── */

function RunsBar({ runs, max }) {
  const pct = max ? Math.round((runs / max) * 100) : 0
  return (
    <div className="h-1.5 rounded-full bg-pb-surface2 overflow-hidden w-full min-w-[40px]">
      <div className="h-full rounded-full" style={{ width: `${pct}%`, background: 'var(--pb-accent)' }} />
    </div>
  )
}

function Trajectory({ seasons }) {
  if (!seasons?.length) return <Empty>No season data.</Empty>
  const maxRuns = Math.max(1, ...seasons.map(s => s.total_runs || 0))
  return (
    <div className="overflow-x-auto -mx-1">
      <table className="w-full text-sm">
        <thead><tr className="text-pb-faint text-[11px] uppercase tracking-wide2 text-left">
          <th className="py-1 px-1 font-medium">Season</th>
          <th className="py-1 px-1 font-medium text-right">M</th>
          <th className="py-1 px-1 font-medium text-right">Runs</th>
          <th className="py-1 px-1 font-medium text-right">Avg</th>
          <th className="py-1 px-1 font-medium w-24">Trend</th>
          <th className="py-1 px-1 font-medium text-right">Wkts</th>
          <th className="py-1 px-1 font-medium text-right">Avg</th>
          <th className="py-1 px-1 font-medium text-right">Econ</th>
        </tr></thead>
        <tbody>
          {seasons.map((s, i) => (
            <tr key={i} className="border-t pb-hairline">
              <td className="py-1.5 px-1 whitespace-nowrap">{s.season_name}</td>
              <td className="py-1.5 px-1 text-right pb-num text-pb-faint">{num(s.matches, 0)}</td>
              <td className="py-1.5 px-1 text-right pb-num font-semibold">{num(s.total_runs, 0)}</td>
              <td className="py-1.5 px-1 text-right pb-num">{num(s.batting_average)}</td>
              <td className="py-1.5 px-1"><RunsBar runs={s.total_runs || 0} max={maxRuns} /></td>
              <td className="py-1.5 px-1 text-right pb-num font-semibold">{num(s.total_wickets, 0)}</td>
              <td className="py-1.5 px-1 text-right pb-num">{num(s.bowling_average)}</td>
              <td className="py-1.5 px-1 text-right pb-num text-pb-faint">{num(s.economy)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function CareerStrip({ career }) {
  const b = career?.batting || {}, bo = career?.bowling || {}, f = career?.fielding || {}
  const items = [
    ['Runs', num(b.total_runs, 0)], ['Bat avg', num(b.average)], ['100s/50s', `${num(b.hundreds, 0)}/${num(b.fifties, 0)}`],
    ['Wkts', num(bo.total_wickets, 0)], ['Bowl avg', num(bo.average)], ['Catches', num(f.total_catches, 0)],
  ]
  return (
    <div className="flex flex-wrap gap-x-6 gap-y-2">
      {items.map(([l, v]) => (
        <div key={l}><div className="font-display font-bold text-lg pb-num leading-none">{v}</div><div className="text-pb-faint text-[10px] uppercase tracking-wide2 mt-0.5">{l}</div></div>
      ))}
    </div>
  )
}

/* ── main ─────────────────────────────────────────────────────────────────── */

export default function PlayerTrends() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [overview, setOverview] = useState(null)
  const [players, setPlayers] = useState([])
  const [playerId, setPlayerId] = useState(searchParams.get('player') || null)
  const [detail, setDetail] = useState(null)
  const [deep, setDeep] = useState(null)
  const [q, setQ] = useState('')

  useEffect(() => {
    api.iqTrendsOverview().then(setOverview).catch(() => setOverview({ milestones: [], batting: {}, bowling: {} }))
    api.iqTrendsPlayers().then(setPlayers).catch(() => setPlayers([]))
  }, [])

  useEffect(() => {
    if (!playerId) { setDetail(null); setDeep(null); return }
    let alive = true
    setDetail(null); setDeep(null)
    api.iqTrendsPlayer(playerId).then(d => { if (alive) setDetail(d) }).catch(() => { if (alive) setDetail({ error: true }) })
    api.iqPlayerDeepDive(playerId).then(d => { if (alive) setDeep(d) }).catch(() => { if (alive) setDeep(null) })
    return () => { alive = false }
  }, [playerId])

  const pick = (id) => { setPlayerId(id); setSearchParams({ player: id }, { replace: true }) }
  const clear = () => { setPlayerId(null); setDetail(null); setDeep(null); setSearchParams({}, { replace: true }) }

  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase()
    return t ? players.filter(p => p.name.toLowerCase().includes(t)) : players
  }, [q, players])

  // ── Detail view ──
  if (playerId) {
    return (
      <IQLayout title="Player trends" actions={<Btn variant="ghost" sm icon="back" onClick={clear}>All players</Btn>}>
        {detail === null && <div className="pb-card p-5 animate-pulse text-pb-faint text-sm">Loading trajectory…</div>}
        {detail?.error && <div className="pb-card p-5"><Empty>Couldn't load this player.</Empty></div>}
        {detail && !detail.error && (
          <>
            <div className="flex flex-wrap items-center gap-2 mb-4">
              <h2 className="font-display font-bold text-2xl">{detail.player.name}</h2>
              <span className="flex items-center gap-1.5">
                {detail.verdict?.batting && <span title="Batting trend"><VerdictTag v={detail.verdict.batting} /></span>}
                {detail.verdict?.bowling && <span title="Bowling trend">🏏<VerdictTag v={detail.verdict.bowling} /></span>}
              </span>
            </div>

            <Card title="Career"><CareerStrip career={detail.career} /></Card>

            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <Card title="Recent form" right={detail.role_evolution ? <Tag tone="accent">{detail.role_evolution}</Tag> : null}>
                <div className="space-y-2 text-sm">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-pb-faint">Last innings</span>
                    <Sparkline values={(detail.recent_form?.batting || []).map(b => b.runs)} />
                  </div>
                  <div className="text-pb-faintest text-[11px] pb-num">{(detail.recent_form?.batting || []).map(b => (b.not_out ? `${b.runs}*` : b.runs)).join(', ') || 'no recent innings'}</div>
                  {(detail.recent_form?.bowling || []).some(w => w > 0) && (
                    <>
                      <div className="flex items-center justify-between gap-3 pt-1">
                        <span className="text-pb-faint">Last spells (wkts)</span>
                        <Sparkline values={detail.recent_form.bowling} />
                      </div>
                      <div className="text-pb-faintest text-[11px] pb-num">{detail.recent_form.bowling.join(', ')}</div>
                    </>
                  )}
                </div>
              </Card>
              <Card title="Career shape">
                <div className="space-y-2 text-sm">
                  {detail.peak?.batting && <div className="flex justify-between gap-2"><span className="text-pb-faint">Best batting season</span><span className="pb-num text-right">{detail.peak.batting.season} · {detail.peak.batting.runs} @ {num(detail.peak.batting.average)}</span></div>}
                  {detail.peak?.bowling && <div className="flex justify-between gap-2"><span className="text-pb-faint">Best bowling season</span><span className="pb-num text-right">{detail.peak.bowling.season} · {detail.peak.bowling.wickets}w @ {num(detail.peak.bowling.average)}</span></div>}
                  {detail.consistency != null && <div className="flex justify-between gap-2"><span className="text-pb-faint">Consistency (σ of season avg)</span><span className="pb-num">±{detail.consistency}</span></div>}
                  {!detail.peak?.batting && !detail.peak?.bowling && <Empty>Not enough history yet.</Empty>}
                </div>
              </Card>
            </div>

            {detail.milestones?.length > 0 && (
              <div className="mt-4">
                <Card title="Closing in on" accent>
                  <div className="flex flex-wrap gap-x-6 gap-y-1.5">
                    {detail.milestones.map((m, i) => (
                      <span key={i} className="text-sm"><b className="pb-num">{m.needed}</b> <span className="text-pb-faint">more {TYPE_LABEL[m.type] || m.type} → {m.target}{m.eta_games ? ` (${fmtEta(m.eta_games)})` : ''}</span></span>
                    ))}
                  </div>
                </Card>
              </div>
            )}

            <div className="mt-4">
              <Card title="Season by season" right={<span className="text-pb-faint text-xs">oldest → newest</span>}>
                <Trajectory seasons={detail.seasons} />
              </Card>
            </div>

            {/* Deep dive — conversion, dismissals, position, opposition (brief §1) */}
            {deep && deep.innings_count > 0 && (
              <>
                {deep.scouting_note && (
                  <div className="mt-4"><Card title="Scouting note" accent><div className="text-sm">{deep.scouting_note}</div></Card></div>
                )}

                <div className="mt-4 grid gap-4 lg:grid-cols-2">
                  {deep.conversion && (
                    <Card title="Starts & conversion" right={<span className="text-pb-faint text-xs">{deep.conversion.innings} innings</span>}>
                      <div className="flex h-2.5 rounded-full overflow-hidden bg-pb-surface2 mb-3">
                        {[['<10', deep.conversion.under_10, 'var(--pb-red)'], ['10–24', deep.conversion.b10_24, 'var(--pb-amber)'], ['25–49', deep.conversion.b25_49, 'var(--pb-dim)'], ['50+', deep.conversion.fifties + deep.conversion.hundreds, 'var(--pb-accent)']].map(([l, v, c]) => (v ? <div key={l} title={`${l}: ${v}`} style={{ flexGrow: v, background: c }} /> : null))}
                      </div>
                      <div className="grid grid-cols-3 gap-2 text-center">
                        <div><div className="font-display font-bold text-lg pb-num">{deep.conversion.start_pct}%</div><div className="text-pb-faint text-[10px] uppercase tracking-wide2">reach 25</div></div>
                        <div><div className="font-display font-bold text-lg pb-num">{deep.conversion.convert_25_to_50 === null ? '—' : `${deep.conversion.convert_25_to_50}%`}</div><div className="text-pb-faint text-[10px] uppercase tracking-wide2">25→50</div></div>
                        <div><div className="font-display font-bold text-lg pb-num">{deep.conversion.fifties}/{deep.conversion.hundreds}</div><div className="text-pb-faint text-[10px] uppercase tracking-wide2">50s/100s</div></div>
                      </div>
                    </Card>
                  )}
                  {deep.dismissals?.length > 0 && (
                    <Card title="How they get out">
                      <div className="space-y-1.5">
                        {deep.dismissals.map(d => (
                          <div key={d.type} className="flex items-center gap-2 text-sm">
                            <span className="w-24 capitalize text-pb-faint shrink-0">{d.type}</span>
                            <div className="flex-1 h-2 rounded-full bg-pb-surface2 overflow-hidden"><div className="h-full rounded-full" style={{ width: `${d.pct}%`, background: 'var(--pb-accent)' }} /></div>
                            <span className="w-10 text-right pb-num shrink-0">{d.pct}%</span>
                          </div>
                        ))}
                      </div>
                    </Card>
                  )}
                </div>

                {deep.selection_value && (
                  <div className="mt-4"><Card title="Selection value" right={<span className="text-pb-faint text-xs">team results</span>}>
                    <div className="grid grid-cols-2 gap-3">
                      <div className="rounded-xl p-3" style={{ background: 'var(--pb-surface2)' }}><div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1">Win % with them</div><div className="font-display font-bold text-2xl pb-num">{deep.selection_value.with.win_pct ?? '—'}%</div><div className="text-pb-faintest text-[11px]">{deep.selection_value.with.games} games</div></div>
                      <div className="rounded-xl p-3" style={{ background: 'var(--pb-surface2)' }}><div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1">Win % without</div><div className="font-display font-bold text-2xl pb-num">{deep.selection_value.without.win_pct ?? '—'}%</div><div className="text-pb-faintest text-[11px]">{deep.selection_value.without.games} games</div></div>
                    </div>
                    {deep.selection_value.swing != null && <div className="text-[12px] mt-2" style={{ color: deep.selection_value.swing >= 0 ? 'var(--pb-brand)' : 'var(--pb-red)' }}>{deep.selection_value.swing >= 0 ? '+' : ''}{deep.selection_value.swing} pts with him in the side.</div>}
                  </Card></div>
                )}

                {deep.similar_players?.length > 0 && (
                  <div className="mt-4"><Card title="Similar players" right={<span className="text-pb-faint text-xs">by profile</span>}>
                    <div className="space-y-0.5">
                      {deep.similar_players.map(s => (
                        <div key={s.player_id} className="flex items-center justify-between gap-3 text-sm py-0.5">
                          <span className="truncate">{s.name}</span>
                          <div className="flex items-center gap-3 whitespace-nowrap pb-num text-pb-faint">
                            {s.bat_avg != null && <span>bat {s.bat_avg}</span>}
                            {s.bowl_avg != null && <span>bowl {s.bowl_avg}</span>}
                            <span className="font-semibold w-12 text-right" style={{ color: 'var(--pb-accent)' }}>{s.similarity}%</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </Card></div>
                )}

                <div className="mt-4 grid gap-4 lg:grid-cols-2">
                  {deep.by_position?.length > 0 && (
                    <Card title="By batting position" right={deep.best_position ? <Tag tone="accent">Best: {deep.best_position}</Tag> : null}>
                      <table className="w-full text-sm">
                        <thead><tr className="text-pb-faint text-[11px] uppercase tracking-wide2 text-left"><th className="py-1 font-medium">Position</th><th className="py-1 font-medium text-right">Inns</th><th className="py-1 font-medium text-right">Runs</th><th className="py-1 font-medium text-right">Avg</th></tr></thead>
                        <tbody>{deep.by_position.map(r => <tr key={r.position} className="border-t pb-hairline"><td className="py-1.5">{r.position}</td><td className="py-1.5 text-right pb-num text-pb-faint">{r.innings}</td><td className="py-1.5 text-right pb-num">{r.runs}</td><td className="py-1.5 text-right pb-num">{num(r.average)}</td></tr>)}</tbody>
                      </table>
                    </Card>
                  )}
                  {(deep.by_opposition?.best?.length > 0 || deep.by_opposition?.worst?.length > 0) && (
                    <Card title="By opposition">
                      <div className="grid sm:grid-cols-2 gap-4 text-sm">
                        <div>
                          <div className="text-pb-faint text-[11px] uppercase tracking-wide2 mb-1">Dominates</div>
                          {deep.by_opposition.best.length ? deep.by_opposition.best.map(o => <div key={o.name} className="flex justify-between gap-2 py-0.5"><span className="truncate">{o.name}</span><span className="pb-num text-pb-faint whitespace-nowrap">{o.runs} @ {num(o.average)}</span></div>) : <Empty>—</Empty>}
                        </div>
                        <div>
                          <div className="text-pb-faint text-[11px] uppercase tracking-wide2 mb-1">Struggles vs</div>
                          {deep.by_opposition.worst.length ? deep.by_opposition.worst.map(o => <div key={o.name} className="flex justify-between gap-2 py-0.5"><span className="truncate">{o.name}</span><span className="pb-num text-pb-faint whitespace-nowrap">{o.runs} @ {num(o.average)}</span></div>) : <Empty>—</Empty>}
                        </div>
                      </div>
                    </Card>
                  )}
                </div>
              </>
            )}
          </>
        )}
      </IQLayout>
    )
  }

  // ── Overview view ──
  return (
    <IQLayout title="Player trends">
      <p className="text-pb-faint text-sm mb-4 max-w-2xl">Who's trending up, who's tailing off, and who's closing in on a milestone — across your active squad.</p>

      <div className="grid gap-4 lg:grid-cols-2 mb-4">
        <Card title="Milestone watch" right={<Tag tone="accent">in reach</Tag>}>
          {overview === null ? <div className="animate-pulse text-pb-faint text-sm">Loading…</div> : <MilestoneList items={overview.milestones} />}
        </Card>
        <Card title="Form movers" right={<span className="text-pb-faint text-xs">latest season vs career</span>}>
          {overview === null ? <div className="animate-pulse text-pb-faint text-sm">Loading…</div> : (
            <div className="grid sm:grid-cols-2 gap-4">
              <Movers title="Batting — rising" rows={overview.batting?.risers} kind="bat" onPick={pick} />
              <Movers title="Batting — declining" rows={overview.batting?.fallers} kind="bat" onPick={pick} />
              <Movers title="Bowling — improving" rows={overview.bowling?.risers} kind="bowl" onPick={pick} />
              <Movers title="Bowling — slipping" rows={overview.bowling?.fallers} kind="bowl" onPick={pick} />
              {!overview.batting?.risers?.length && !overview.batting?.fallers?.length && !overview.bowling?.risers?.length && !overview.bowling?.fallers?.length && (
                <div className="sm:col-span-2"><Empty>Not enough multi-season history to spot movers yet.</Empty></div>
              )}
            </div>
          )}
        </Card>
      </div>

      {overview?.emerging?.length > 0 && (
        <div className="mb-4">
          <Card title="Emerging — ones to watch" accent right={<span className="text-pb-faint text-xs">few seasons, strong form</span>}>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {overview.emerging.map(p => (
                <button key={p.player_id} onClick={() => pick(p.player_id)}
                  className="pb-card px-3 py-2 text-left hover:border-pb-accent/50 transition-colors flex items-center justify-between gap-2">
                  <span className="font-medium truncate">{p.name}</span>
                  <span className="text-pb-faintest text-[11px] pb-num whitespace-nowrap">{p.runs}r · {p.wickets}w · {p.seasons}s</span>
                </button>
              ))}
            </div>
          </Card>
        </div>
      )}

      <Card title={`Players (${players.length})`}>
        <Search value={q} onChange={setQ} placeholder="Search players…" className="mb-3 max-w-sm" />
        {filtered.length === 0 ? <Empty>No players.</Empty> : (
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map(p => (
              <button key={p.player_id} onClick={() => pick(p.player_id)}
                className="pb-card px-3 py-2 text-left hover:border-pb-accent/50 transition-colors flex items-center justify-between gap-2">
                <span className="font-medium truncate">{p.name}</span>
                <span className="text-pb-faintest text-[11px] pb-num whitespace-nowrap">{p.runs} runs · {p.wickets} wkts</span>
              </button>
            ))}
          </div>
        )}
      </Card>
    </IQLayout>
  )
}
