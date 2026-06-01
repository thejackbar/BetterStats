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

const AVAIL = {
  AVAILABLE: ['Avail', 'var(--pb-brand)'],
  UNAVAILABLE: ['Out', 'var(--pb-red)'],
  MAYBE: ['Maybe', 'var(--pb-amber)'],
}
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

/* ── balance summary ──────────────────────────────────────────────────────── */
function Balance({ b }) {
  if (!b) return null
  return (
    <Card title="XI balance">
      <div className="flex flex-wrap items-center gap-1 sm:gap-2">
        <Stat label="In XI" value={b.size} tone={b.size === 11 ? undefined : 'var(--pb-amber)'} />
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

/* ── warnings ─────────────────────────────────────────────────────────────── */
function Warnings({ warnings }) {
  if (!warnings?.length) return (
    <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--pb-brand)' }}>
      <Icon name="check" size={16} /> No balance flags — looks like a well-rounded XI.
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
function XITable({ players }) {
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
          <th className="py-1 px-1 font-medium text-right">Season</th>
          <th className="py-1 px-1 font-medium">Avail</th>
        </tr></thead>
        <tbody>
          {players.map(p => (
            <tr key={p.player_id} className="border-t pb-hairline">
              <td className="py-1.5 px-1 pb-num text-pb-faint">{num(p.batting_order, '·')}</td>
              <td className="py-1.5 px-1 font-medium whitespace-nowrap">
                {p.name}
                {p.is_captain && <Tag tone="accent" className="ml-1">C</Tag>}
                {p.is_wicket_keeper && <Tag tone="amber" className="ml-1">WK</Tag>}
                {' '}<UpDown d={p.play_updown} />
              </td>
              <td className="py-1.5 px-1 text-pb-faint text-[11px] font-mono">{(p.skills || []).join(' ') || '—'}{p.bowling_type ? ` · ${p.bowling_type.toLowerCase().replace('_', ' ')}` : ''}</td>
              <td className="py-1.5 px-1 text-pb-faint pb-num text-[11px] whitespace-nowrap">
                {(p.recent_scores || []).join(' ') || '—'}
                {p.recent_wickets?.some(w => w !== '0') ? <span className="text-pb-faintest"> · {p.recent_wickets.join('')}w</span> : ''}
              </td>
              <td className="py-1.5 px-1 text-right pb-num">{num(p.recent_avg)}</td>
              <td className="py-1.5 px-1 text-right pb-num text-pb-faint">{num(p.season_matches, 0)}</td>
              <td className="py-1.5 px-1"><AvailDot status={p.availability} /></td>
            </tr>
          ))}
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
  if (!rows.length) return (
    <Empty>No saved lineups yet. Pick a team for an upcoming fixture in BetterSelect, then come back to analyse it.</Empty>
  )
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

  useEffect(() => {
    api.iqSelectionLineups().then(setRows).catch(() => setRows([]))
  }, [])

  useEffect(() => {
    if (!fixtureId) { setData(null); return }
    let alive = true
    setData(null); setErr(false)
    api.iqSelectionAnalysis(fixtureId)
      .then(d => { if (alive) setData(d) })
      .catch(() => { if (alive) setErr(true) })
    return () => { alive = false }
  }, [fixtureId])

  const pick = (id) => { setFixtureId(id); setSearchParams({ fixture: id }, { replace: true }) }
  const clear = () => { setFixtureId(null); setData(null); setSearchParams({}, { replace: true }) }

  if (!fixtureId) {
    return (
      <IQLayout title="Selection analysis">
        <p className="text-pb-faint text-sm mb-4 max-w-2xl">BetterSelect picks the team — BetterIQ checks the balance and justifies the pick. Choose a fixture with a saved lineup.</p>
        {rows === null
          ? <div className="pb-card p-5 animate-pulse text-pb-faint text-sm">Loading lineups…</div>
          : <LineupPicker rows={rows} onPick={pick} />}
      </IQLayout>
    )
  }

  const fx = data?.fixture
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
          </div>

          <div className="grid gap-4 lg:grid-cols-2 mb-4">
            <Balance b={data.balance} />
            <Card title="Selection check"><Warnings warnings={data.warnings} /></Card>
          </div>

          <Card title="The XI" right={<span className="text-pb-faint text-xs">form = last 5</span>}>
            <XITable players={data.players} />
          </Card>

          <div className="grid gap-4 lg:grid-cols-2 mt-4">
            <Card title="Promote — in form, left out" accent>
              {data.promote?.length ? (
                <div className="space-y-2">
                  {data.promote.map(p => (
                    <div key={p.player_id} className="flex items-center justify-between gap-2">
                      <div className="min-w-0">
                        <span className="font-medium">{p.name}</span> <UpDown d={p.play_updown} />
                        <div className="text-pb-faintest text-[11px]">{(p.recent_scores || []).join(', ') || 'no recent bat'}{p.recent_wickets?.some(w => w !== '0') ? ` · ${p.recent_wickets.join('')}w` : ''}</div>
                      </div>
                      <AvailDot status={p.available} />
                    </div>
                  ))}
                </div>
              ) : <Empty>No clear in-form players left out.</Empty>}
            </Card>
            <Card title="Watch — out of form in the XI">
              {data.rest?.length ? (
                <div className="space-y-2">
                  {data.rest.map(p => (
                    <div key={p.player_id} className="flex items-center justify-between gap-2">
                      <span className="font-medium">{p.name}</span>
                      <span className="text-pb-faint text-sm pb-num">{(p.recent_scores || []).join(', ')} · avg {num(p.recent_avg)}</span>
                    </div>
                  ))}
                </div>
              ) : <Empty>Nobody picked is conspicuously out of form.</Empty>}
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
