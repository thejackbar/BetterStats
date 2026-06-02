import { useState, useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import IQLayout from '../../../components/admin/IQLayout'
import { api } from '../../../lib/api'
import { Icon, Btn, Tag, Empty, Search } from '../betterselect/ui'

const num = (v, dash = '—') => (v === null || v === undefined ? dash : v)

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

function Stat({ label, value, tone }) {
  return (
    <div className="text-center px-2.5 py-1.5">
      <div className="font-display font-bold text-xl pb-num leading-none" style={tone ? { color: tone } : undefined}>{value}</div>
      <div className="text-pb-faint text-[10px] mt-1 uppercase tracking-wide2">{label}</div>
    </div>
  )
}

const AVAIL = { AVAILABLE: ['Avail', 'var(--pb-brand)'], UNAVAILABLE: ['Out', 'var(--pb-red)'], MAYBE: ['Maybe', 'var(--pb-amber)'] }
function AvailDot({ status }) {
  if (!status || status === 'NO_RESPONSE') return <span className="text-pb-faintest text-[11px]">—</span>
  const [label, color] = AVAIL[status] || ['?', 'var(--pb-faint)']
  return <span className="font-mono text-[10px] px-1.5 py-0.5 rounded" style={{ background: `color-mix(in srgb, ${color} 16%, transparent)`, color }}>{label}</span>
}

function UpDown({ d }) {
  if (!d) return null
  const up = d === 'up'
  return <span title={up ? 'Playing up a grade' : 'Dropping down a grade'} className="font-mono text-[10px]" style={{ color: up ? 'var(--pb-amber)' : 'var(--pb-faint)' }}>{up ? '▲ up' : '▼ down'}</span>
}

const FLAG_META = {
  'wrong-grade': ['Wrong grade', 'var(--pb-red)'],
  inactive: ['Inactive', 'var(--pb-red)'],
  dormant: ['Dormant', 'var(--pb-amber)'],
  unavailable: ['Unavailable', 'var(--pb-red)'],
}
function Flags({ flags }) {
  if (!flags?.length) return null
  return (
    <span className="inline-flex gap-1 ml-1">
      {flags.map(f => {
        const [label, color] = FLAG_META[f] || [f, 'var(--pb-faint)']
        return <span key={f} className="font-mono text-[9px] px-1 py-0.5 rounded" style={{ background: `color-mix(in srgb, ${color} 16%, transparent)`, color }}>{label}</span>
      })}
    </span>
  )
}

// Recent batting scores as "75, 74*, 12"; recent wickets summarised as "9w/5".
function recentBat(p) { return (p.recent_scores || []).join(', ') || '—' }
function recentBowl(p) {
  const w = p.recent_wickets || []
  const t = w.reduce((a, b) => a + (b || 0), 0)
  return t > 0 ? `${t}w/${w.length}` : null
}
function VsOpp({ v }) {
  if (!v) return <span className="text-pb-faintest">—</span>
  return (
    <span className="pb-num text-[11px]">
      {v.bat ? <span title={`${v.bat.runs} runs @ ${num(v.bat.avg)} vs them`}>{v.bat.runs}@{num(v.bat.avg)}</span> : null}
      {v.bat && v.bowl ? ' · ' : ''}
      {v.bowl ? <span title={`${v.bowl.wickets} wkts @ ${num(v.bowl.avg)} vs them`}>{v.bowl.wickets}w@{num(v.bowl.avg)}</span> : null}
    </span>
  )
}

/* ── balance ──────────────────────────────────────────────────────────────── */
function Balance({ b, target }) {
  if (!b) return null
  return (
    <Card title="XI balance">
      <div className="flex flex-wrap items-center gap-1 sm:gap-2">
        <Stat label="In XI" value={b.size} tone={target && b.size !== target ? 'var(--pb-amber)' : undefined} />
        <Stat label="Batters" value={b.specialist_batters} />
        <Stat label="All-round" value={b.all_rounders} />
        <Stat label="Bowlers" value={b.bowling_options} tone={b.bowling_options < 5 ? 'var(--pb-amber)' : undefined} />
        <Stat label="Pace/Spin" value={`${b.pace}/${b.spin}`} />
        <Stat label="Keeper" value={b.keepers} tone={b.keepers === 0 ? 'var(--pb-red)' : undefined} />
        <Stat label="Openers" value={b.openers} />
        <Stat label="LH/RH" value={`${b.left_hand_bat}/${b.right_hand_bat}`} />
      </div>
    </Card>
  )
}

function Warnings({ warnings }) {
  if (!warnings?.length) return (
    <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--pb-brand)' }}>
      <Icon name="check" size={16} /> No balance flags — a well-rounded XI.
    </div>
  )
  return (
    <div className="space-y-1.5">
      {warnings.map((w, i) => {
        const color = w.level === 'warn' ? 'var(--pb-red)' : 'var(--pb-amber)'
        return (
          <div key={i} className="flex items-start gap-2 text-sm">
            <Icon name="info" size={15} className="mt-0.5 shrink-0" style={{ color }} />
            <span className={w.level === 'warn' ? 'text-pb-text' : 'text-pb-faint'}>{w.text}</span>
          </div>
        )
      })}
    </div>
  )
}

/* ── XI table ─────────────────────────────────────────────────────────────── */
function XITable({ players, oppLabel }) {
  if (!players?.length) return <Empty>No players in this lineup yet.</Empty>
  return (
    <div className="overflow-x-auto -mx-1">
      <table className="w-full text-sm">
        <thead><tr className="text-pb-faint text-[11px] uppercase tracking-wide2 text-left">
          <th className="py-1 px-1 font-medium">#</th>
          <th className="py-1 px-1 font-medium">Player</th>
          <th className="py-1 px-1 font-medium">Role</th>
          <th className="py-1 px-1 font-medium">Recent</th>
          <th className="py-1 px-1 font-medium text-right">Form avg</th>
          {oppLabel && <th className="py-1 px-1 font-medium text-right">vs {oppLabel}</th>}
          <th className="py-1 px-1 font-medium">Avail</th>
        </tr></thead>
        <tbody>
          {players.map(p => {
            const rb = recentBowl(p)
            return (
              <tr key={p.player_id} className="border-t pb-hairline">
                <td className="py-1.5 px-1 pb-num text-pb-faint">{num(p.batting_order, '·')}</td>
                <td className="py-1.5 px-1 font-medium whitespace-nowrap">
                  {p.name}
                  {p.is_captain && <Tag tone="accent" className="ml-1">C</Tag>}
                  {p.is_wicket_keeper && <Tag tone="amber" className="ml-1">WK</Tag>}
                  {' '}<UpDown d={p.play_updown} /><Flags flags={p.flags} />
                </td>
                <td className="py-1.5 px-1 text-pb-faint text-[11px] font-mono">{(p.skills || []).join(' ') || '—'}{p.bowling_type ? ` · ${p.bowling_type.toLowerCase().replace(/_/g, ' ')}` : ''}</td>
                <td className="py-1.5 px-1 text-pb-faint pb-num text-[11px] whitespace-nowrap">
                  {recentBat(p)}{rb ? <span className="text-pb-faintest"> · {rb}</span> : ''}
                </td>
                <td className="py-1.5 px-1 text-right pb-num">{num(p.recent_avg)}</td>
                {oppLabel && <td className="py-1.5 px-1 text-right text-pb-faint"><VsOpp v={p.vs_opponent} /></td>}
                <td className="py-1.5 px-1"><AvailDot status={p.availability} /></td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

/* ── picker ───────────────────────────────────────────────────────────────── */
function LineupPicker({ rows, onPick }) {
  const [q, setQ] = useState('')
  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase()
    return t ? rows.filter(r => (r.opponent_name || '').toLowerCase().includes(t) || (r.team_name || '').toLowerCase().includes(t)) : rows
  }, [q, rows])
  if (!rows.length) return <Empty>No saved lineups yet. Pick a team for a fixture in BetterSelect, then analyse it here.</Empty>
  return (
    <div>
      <Search value={q} onChange={setQ} placeholder="Search fixtures…" className="mb-3 max-w-sm" />
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {filtered.map(r => (
          <button key={r.fixture_id} onClick={() => onPick(r.fixture_id)}
            className="pb-card px-3 py-2.5 text-left hover:border-pb-accent/50 transition-colors">
            <div className="font-medium truncate">{r.team_name || 'Team'} <span className="text-pb-faint">vs</span> {r.opponent_name || 'TBC'}</div>
            <div className="text-pb-faintest text-[11px] mt-0.5 flex flex-wrap gap-x-2">
              {r.played_on && <span>{r.played_on}</span>}
              {r.home_away && <span className="font-mono uppercase">{r.home_away}</span>}
              <span>· {r.lineup_count} picked</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}

/* ── main ─────────────────────────────────────────────────────────────────── */
export default function SelectionAnalysis() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [rows, setRows] = useState(null)
  const [fixtureId, setFixtureId] = useState(searchParams.get('fixture') || null)
  const [data, setData] = useState(null)
  const [err, setErr] = useState(false)

  useEffect(() => { api.iqSelectionLineups().then(setRows).catch(() => setRows([])) }, [])

  useEffect(() => {
    if (!fixtureId) { setData(null); return }
    let alive = true
    setData(null); setErr(false)
    api.iqSelectionAnalysis(fixtureId).then(d => { if (alive) setData(d) }).catch(() => { if (alive) setErr(true) })
    return () => { alive = false }
  }, [fixtureId])

  const pick = (id) => { setFixtureId(id); setSearchParams({ fixture: id }, { replace: true }) }
  const clear = () => { setFixtureId(null); setData(null); setSearchParams({}, { replace: true }) }

  if (!fixtureId) {
    return (
      <IQLayout title="Selection analysis">
        <p className="text-pb-faint text-sm mb-4 max-w-2xl">BetterSelect picks the team — BetterIQ checks the balance and justifies the pick. Choose a fixture with a saved lineup.</p>
        {rows === null ? <div className="pb-card p-5 animate-pulse text-pb-faint text-sm">Loading lineups…</div> : <LineupPicker rows={rows} onPick={pick} />}
      </IQLayout>
    )
  }

  const fx = data?.fixture
  const oppLabel = fx?.opponent_resolved_name || (fx?.opponent_key ? fx?.opponent_name : null)
  return (
    <IQLayout title="Selection analysis" actions={<Btn variant="ghost" sm icon="back" onClick={clear}>Change fixture</Btn>}>
      {data === null && !err && <div className="pb-card p-5 animate-pulse text-pb-faint text-sm">Analysing the XI…</div>}
      {err && <div className="pb-card p-5"><Empty>Couldn't load this lineup. It may have been removed — pick another fixture.</Empty></div>}
      {data && (
        <>
          <div className="mb-4">
            <div className="font-mono text-[11px] uppercase tracking-wide3" style={{ color: 'var(--pb-accent)' }}>Selection report</div>
            <h2 className="font-display font-bold text-2xl">{fx.team_name || 'Team'} vs {fx.opponent_name || 'TBC'}</h2>
            <div className="text-pb-faint text-xs mt-0.5 flex flex-wrap gap-x-2">
              {fx.played_on && <span>{fx.played_on}</span>}
              {fx.home_away && <span className="font-mono uppercase">{fx.home_away}</span>}
              {fx.grade_name && <span>· {fx.grade_name}</span>}
              {fx.venue && <span>· {fx.venue}</span>}
            </div>
            {data.verdict && <div className="text-sm mt-2 font-medium">{data.verdict}</div>}
          </div>

          <div className="grid gap-4 lg:grid-cols-2 mb-4">
            <Balance b={data.balance} target={data.team_size_target} />
            <Card title="Selection check"><Warnings warnings={data.warnings} /></Card>
          </div>

          <Card title="The XI" right={<span className="text-pb-faint text-xs">form = last 5</span>}>
            <XITable players={data.players} oppLabel={oppLabel} />
          </Card>

          <div className="grid gap-4 lg:grid-cols-2 mt-4">
            <Card title="Promote — in form, eligible, left out" accent>
              {data.promote?.length ? (
                <div className="space-y-2">
                  {data.promote.map(p => {
                    const rb = recentBowl(p)
                    return (
                      <div key={p.player_id} className="flex items-center justify-between gap-2">
                        <div className="min-w-0">
                          <span className="font-medium">{p.name}</span> <UpDown d={p.play_updown} />
                          <div className="text-pb-faintest text-[11px]">
                            {recentBat(p)}{rb ? ` · ${rb}` : ''}{p.vs_opponent?.bat ? ` · ${p.vs_opponent.bat.runs} vs them` : ''}
                          </div>
                        </div>
                        <AvailDot status={p.availability} />
                      </div>
                    )
                  })}
                </div>
              ) : <Empty>No eligible, in-form players are being left out.</Empty>}
            </Card>
            <Card title="Watch — ineligible or out of form">
              {data.rest?.length ? (
                <div className="space-y-2">
                  {data.rest.map(p => (
                    <div key={p.player_id} className="flex items-center justify-between gap-2">
                      <div className="min-w-0"><span className="font-medium">{p.name}</span>
                        <div className="text-pb-faintest text-[11px]">{p.reason}</div>
                      </div>
                      <span className="text-pb-faint text-sm pb-num">{recentBat(p)}{p.recent_avg != null ? ` · avg ${p.recent_avg}` : ''}</span>
                    </div>
                  ))}
                </div>
              ) : <Empty>Nobody picked is out of form or ineligible.</Empty>}
            </Card>
          </div>

          <div className="mt-4">
            <Card title="Suggested best available XI" accent right={<span className="text-pb-faint text-xs">from eligible, available players</span>}>
              {data.best_xi?.length ? (
                <>
                  <div className="flex flex-wrap gap-1.5 mb-3">
                    {data.best_xi.map(p => (
                      <span key={p.player_id}
                        title={p.in_xi ? 'Already in your XI' : 'Suggested addition'}
                        className="inline-flex items-center gap-1 px-2 py-1 rounded text-[12px]"
                        style={p.in_xi
                          ? { background: 'var(--pb-surface2)', color: 'var(--pb-faint)' }
                          : { background: 'color-mix(in srgb, var(--pb-accent) 14%, transparent)', color: 'var(--pb-accent)' }}>
                        {p.name}{!p.in_xi && ' +'}
                      </span>
                    ))}
                  </div>
                  <div className="grid sm:grid-cols-2 gap-4 text-sm">
                    <div>
                      <div className="text-pb-faint text-[11px] uppercase tracking-wide2 mb-1">Consider adding</div>
                      {data.suggest_in?.length ? data.suggest_in.map(p => (
                        <div key={p.player_id} className="flex items-center justify-between py-0.5">
                          <span>{p.name} <UpDown d={p.play_updown} /></span>
                          <span className="text-pb-faintest text-[11px] pb-num">{(p.recent_scores || []).slice(-3).join(', ')}</span>
                        </div>
                      )) : <Empty>Your XI already matches the best available.</Empty>}
                    </div>
                    <div>
                      <div className="text-pb-faint text-[11px] uppercase tracking-wide2 mb-1">Picked, not in best XI</div>
                      {data.suggest_out?.length ? data.suggest_out.map(p => (
                        <div key={p.player_id} className="flex items-center justify-between py-0.5">
                          <span>{p.name}</span><Flags flags={p.flags} />
                        </div>
                      )) : <Empty>—</Empty>}
                    </div>
                  </div>
                </>
              ) : <Empty>Not enough eligible, available players to build a suggested XI.</Empty>}
            </Card>
          </div>

          {data.coverage?.notes?.length > 0 && (
            <div className="text-pb-faintest text-[11px] mt-3 flex items-start gap-1.5">
              <Icon name="info" size={13} className="mt-0.5 shrink-0" />
              <span>{data.coverage.notes.join(' ')}</span>
            </div>
          )}
        </>
      )}
    </IQLayout>
  )
}
