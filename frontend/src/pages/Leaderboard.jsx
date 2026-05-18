import { useParams, Link } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { useClubData } from '../hooks/useClubData'
import { useClub } from '../hooks/useClub'
import { useClubTheme } from '../hooks/useClubTheme'
import { usePageMeta } from '../hooks/usePageMeta'
import { api } from '../lib/api'
import ClubInactive from './ClubInactive'
import SeasonSelector from '../components/SeasonSelector'
import {
  Label, Card, PageHeader, PbSpinner,
} from '../lib/presskit'
import { useNameFormat } from '../lib/nameFormat'

const BATTING_SORTS = [
  { key: 'total_runs',    label: 'MOST RUNS' },
  { key: 'average',       label: 'AVERAGE' },
  { key: 'high_score',    label: 'HIGH SCORE' },
  { key: 'fifties',       label: 'FIFTIES' },
  { key: 'hundreds',      label: 'CENTURIES' },
  { key: 'total_sixes',   label: 'SIXES' },
  { key: 'total_fours',   label: 'FOURS' },
  { key: 'ducks',         label: 'DUCKS' },
]

const BOWLING_SORTS = [
  { key: 'total_wickets',        label: 'WICKETS' },
  { key: 'economy',              label: 'ECONOMY' },
  { key: 'average',              label: 'AVERAGE' },
  { key: 'best_figures_wickets', label: 'BEST FIGURES' },
  { key: 'five_fors',            label: 'FIVE-FORS' },
  { key: 'total_maidens',        label: 'MAIDENS' },
]

const FIELDING_SORTS = [
  { key: 'total_catches',   label: 'CATCHES' },
  { key: 'total_run_outs',  label: 'RUN OUTS' },
  { key: 'total_stumpings', label: 'STUMPINGS' },
]

const MAIN_TABS = [
  { key: 'batting',  label: 'BATTING' },
  { key: 'bowling',  label: 'BOWLING' },
  { key: 'fielding', label: 'FIELDING' },
]

function MinFilterInput({ label, value, onChange }) {
  return (
    <div className="flex items-center gap-2 px-1 py-2 mb-3">
      <span className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">{label}</span>
      <input
        type="number"
        min="0"
        value={value}
        onChange={e => onChange(Math.max(0, parseInt(e.target.value) || 0))}
        className="w-20 px-2 py-1 rounded text-[12px] font-mono text-pb-text bg-pb-surface2 border border-pb-hairline focus:outline-none focus:border-pb-accent text-right"
      />
    </div>
  )
}

function SortBtn({ label, active, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`relative px-3.5 py-2.5 text-[11px] font-mono font-semibold tracking-wide3 transition ${
        active ? 'text-pb-text' : 'text-pb-faint hover:text-pb-dim'
      }`}
    >
      {label}
      {active && <span className="absolute left-2 right-2 -bottom-px h-[2px]" style={{ background: 'var(--pb-accent)' }} />}
    </button>
  )
}

// Columns to show for each batting sort type
function getBattingCols(sortBy) {
  const base = ['M', 'RUNS', 'AVG', 'HS']
  if (sortBy === 'average')     return ['M', 'AVG', 'RUNS', 'INN', 'HS']
  if (sortBy === 'high_score')  return ['M', 'HS', 'RUNS', 'AVG']
  if (sortBy === 'fifties')     return ['M', '50s', 'RUNS', 'AVG']
  if (sortBy === 'hundreds')    return ['M', '100s', 'RUNS', 'AVG']
  if (sortBy === 'total_sixes') return ['M', '6s', 'RUNS']
  if (sortBy === 'total_fours') return ['M', '4s', 'RUNS']
  if (sortBy === 'ducks')       return ['M', 'DUCKS', 'INN']
  return base
}

function BattingTable({ rows, sortBy, fmt = n => n }) {
  const primaryLabel = BATTING_SORTS.find(s => s.key === sortBy)?.label || 'VALUE'
  const primaryKey = sortBy || 'total_runs'
  const cols = getBattingCols(sortBy)

  return (
    <Card pad="p-0">
      <div className="overflow-x-auto pb-scroll">
        <table className="w-full min-w-[560px] text-[14px]">
          <thead>
            <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left bg-pb-surface2/40">
              <th className="font-medium py-3 pl-5 w-10">#</th>
              <th className="font-medium py-3">PLAYER</th>
              {cols.map(c => (
                <th key={c} className="font-medium py-3 text-right pr-3"
                  style={c === primaryLabel || c === 'RUNS' || c === 'AVG' || c === 'INN' || c === 'HS' || c === '50s' || c === '100s' || c === '6s' || c === '4s' || c === 'DUCKS' || c === 'M'
                    ? (c === primaryLabel || (c === 'RUNS' && sortBy === 'total_runs') || (c === 'AVG' && sortBy === 'average') || (c === 'HS' && sortBy === 'high_score') || (c === '50s' && sortBy === 'fifties') || (c === '100s' && sortBy === 'hundreds') || (c === '6s' && sortBy === 'total_sixes') || (c === '4s' && sortBy === 'total_fours') || (c === 'DUCKS' && sortBy === 'ducks'))
                      ? { color: 'var(--pb-accent)' } : {}
                    : {}
                  }>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((p, i) => (
              <tr key={p.player_id} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                <td className="py-3 pl-5 font-mono text-pb-faint">{String(i + 1).padStart(2, '0')}</td>
                <td className="py-3">
                  <Link to={`/players/${p.player_id}`} className="text-pb-text font-semibold hover:text-pb-accent">{fmt(p.name)}</Link>
                </td>
                {cols.map(c => {
                  let val
                  const isPrimary = (c === 'RUNS' && sortBy === 'total_runs') || (c === 'AVG' && sortBy === 'average') || (c === 'HS' && sortBy === 'high_score') || (c === '50s' && sortBy === 'fifties') || (c === '100s' && sortBy === 'hundreds') || (c === '6s' && sortBy === 'total_sixes') || (c === '4s' && sortBy === 'total_fours') || (c === 'DUCKS' && sortBy === 'ducks')
                  if (c === 'M')    val = p.games ?? '—'
                  else if (c === 'RUNS')  val = p.total_runs ?? '—'
                  else if (c === 'INN')   val = p.innings ?? '—'
                  else if (c === 'AVG')   val = p.average != null ? Number(p.average).toFixed(2) : '—'
                  else if (c === 'HS')    val = p.high_score ?? '—'
                  else if (c === '50s')   val = p.fifties ?? '—'
                  else if (c === '100s')  val = p.hundreds ?? '—'
                  else if (c === '6s')    val = p.total_sixes ?? '—'
                  else if (c === '4s')    val = p.total_fours ?? '—'
                  else if (c === 'DUCKS') val = p.ducks ?? '—'
                  return (
                    <td key={c} className="py-3 pr-3 font-mono text-right">
                      <span className={isPrimary ? 'text-[15px] font-bold pb-num' : 'text-pb-dim'}
                            style={isPrimary ? { color: 'var(--pb-accent)' } : {}}>
                        {val}
                      </span>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function BowlingTable({ rows, sortBy, fmt = n => n }) {
  return (
    <Card pad="p-0">
      <div className="overflow-x-auto pb-scroll">
        <table className="w-full min-w-[560px] text-[14px]">
          <thead>
            <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left bg-pb-surface2/40">
              <th className="font-medium py-3 pl-5 w-10">#</th>
              <th className="font-medium py-3">PLAYER</th>
              <th className="font-medium py-3 text-right pr-3">M</th>
              <th className="font-medium py-3 text-right pr-3" style={{ color: 'var(--pb-accent)' }}>
                {BOWLING_SORTS.find(s => s.key === sortBy)?.label || 'WICKETS'}
              </th>
              {sortBy !== 'total_wickets' && <th className="font-medium py-3 text-right pr-3">WKTS</th>}
              <th className="font-medium py-3 text-right pr-3">AVG</th>
              <th className="font-medium py-3 text-right pr-3">ECON</th>
              <th className="font-medium py-3 pr-5 text-right">BEST</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p, i) => (
              <tr key={p.player_id} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                <td className="py-3 pl-5 font-mono text-pb-faint">{String(i + 1).padStart(2, '0')}</td>
                <td className="py-3">
                  <Link to={`/players/${p.player_id}`} className="text-pb-text font-semibold hover:text-pb-accent">{fmt(p.name)}</Link>
                </td>
                <td className="py-3 pr-3 font-mono text-pb-dim text-right">{p.games ?? '—'}</td>
                <td className="py-3 pr-3 text-right">
                  <span className="font-mono text-[15px] font-bold pb-num" style={{ color: 'var(--pb-accent)' }}>
                    {sortBy === 'best_figures_wickets'
                      ? (p.best_bowling_figures ? p.best_bowling_figures.replace('-', '/') : p.best_figures_wickets != null ? `${p.best_figures_wickets}w` : '—')
                      : (p[sortBy] ?? '—')}
                  </span>
                </td>
                {sortBy !== 'total_wickets' && (
                  <td className="py-3 pr-3 font-mono text-pb-text text-right">{p.total_wickets ?? '—'}</td>
                )}
                <td className="py-3 pr-3 font-mono text-pb-dim text-right">{p.average != null ? Number(p.average).toFixed(2) : '—'}</td>
                <td className="py-3 pr-3 font-mono text-pb-dim text-right">{p.economy != null ? Number(p.economy).toFixed(2) : '—'}</td>
                <td className="py-3 pr-5 font-mono text-pb-dim text-right">
                  {p.best_bowling_figures ? p.best_bowling_figures.replace('-', '/') : p.best_figures_wickets != null ? `${p.best_figures_wickets}w` : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function FieldingTable({ rows, sortBy, fmt = n => n }) {
  const primaryLabel = FIELDING_SORTS.find(s => s.key === sortBy)?.label || 'CATCHES'
  const primaryKey = sortBy || 'total_catches'

  return (
    <Card pad="p-0">
      <div className="overflow-x-auto pb-scroll">
        <table className="w-full min-w-[460px] text-[14px]">
          <thead>
            <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left bg-pb-surface2/40">
              <th className="font-medium py-3 pl-5 w-10">#</th>
              <th className="font-medium py-3">PLAYER</th>
              <th className="font-medium py-3 text-right pr-3">M</th>
              <th className="font-medium py-3 text-right pr-3" style={{ color: 'var(--pb-accent)' }}>{primaryLabel}</th>
              {sortBy !== 'total_catches'   && <th className="font-medium py-3 text-right pr-3">CATCHES</th>}
              {sortBy !== 'total_run_outs'  && <th className="font-medium py-3 text-right pr-3">RUN OUTS</th>}
              {sortBy !== 'total_stumpings' && <th className="font-medium py-3 pr-5 text-right">STUMPINGS</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((p, i) => (
              <tr key={p.player_id} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                <td className="py-3 pl-5 font-mono text-pb-faint">{String(i + 1).padStart(2, '0')}</td>
                <td className="py-3">
                  <Link to={`/players/${p.player_id}`} className="text-pb-text font-semibold hover:text-pb-accent">{fmt(p.name)}</Link>
                </td>
                <td className="py-3 pr-3 font-mono text-pb-dim text-right">{p.games ?? '—'}</td>
                <td className="py-3 pr-3 text-right">
                  <span className="font-mono text-[15px] font-bold pb-num" style={{ color: 'var(--pb-accent)' }}>
                    {p[primaryKey] ?? '—'}
                  </span>
                </td>
                {sortBy !== 'total_catches'   && <td className="py-3 pr-3 font-mono text-pb-dim text-right">{p.total_catches ?? '—'}</td>}
                {sortBy !== 'total_run_outs'  && <td className="py-3 pr-3 font-mono text-pb-dim text-right">{p.total_run_outs ?? '—'}</td>}
                {sortBy !== 'total_stumpings' && <td className="py-3 pr-5 font-mono text-pb-dim text-right">{p.total_stumpings ?? '—'}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

export default function Leaderboard() {
  const { clubSlug } = useParams()
  const { club, orgId, inactive } = useClub(clubSlug)
  useClubTheme(club)
  const fmt = useNameFormat(club)
  usePageMeta({
    title: club?.name ? `${club.name} Leaderboard — BetterStats` : null,
    description: club?.name ? `Top batting, bowling, and fielding statistics for ${club.name}.` : null,
    image: club?.logo_url || null,
  })

  if (inactive) return <ClubInactive />

  const { org, seasons, selectedSeason, setSelectedSeason, loading: clubLoading } = useClubData(orgId)

  const [orgGrades, setOrgGrades] = useState([])
  const [selectedGradeName, setSelectedGradeName] = useState(null)

  const [mainTab, setMainTab] = useState('batting')
  const [battingSort, setBattingSort] = useState('total_runs')
  const [bowlingSort, setBowlingSort] = useState('total_wickets')
  const [fieldingSort, setFieldingSort] = useState('total_catches')

  const [minRuns, setMinRuns] = useState(500)
  const [minOvers, setMinOvers] = useState(100)
  const [minWickets, setMinWickets] = useState(50)

  const [battingRows, setBattingRows] = useState([])
  const [bowlingRows, setBowlingRows] = useState([])
  const [fieldingRows, setFieldingRows] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!orgId) return
    api.getOrgGrades(orgId).then(setOrgGrades).catch(() => setOrgGrades([]))
  }, [orgId])

  const effectiveMinRuns = battingSort === 'average' ? minRuns : 0
  const effectiveMinOvers = bowlingSort === 'economy' ? minOvers : 0
  const effectiveMinWickets = bowlingSort === 'average' ? minWickets : 0

  useEffect(() => {
    if (!orgId) return
    setLoading(true)
    Promise.allSettled([
      api.battingLeaderboard(orgId, { seasonId: selectedSeason, gradeName: selectedGradeName, sortBy: battingSort, limit: 30, minRuns: effectiveMinRuns }),
      api.bowlingLeaderboard(orgId, { seasonId: selectedSeason, gradeName: selectedGradeName, sortBy: bowlingSort, limit: 30, minOvers: effectiveMinOvers, minWickets: effectiveMinWickets }),
      api.fieldingLeaderboard(orgId, { seasonId: selectedSeason, gradeName: selectedGradeName, sortBy: fieldingSort, limit: 30 }),
    ]).then(([b, bw, f]) => {
      if (b.status === 'fulfilled') setBattingRows(b.value)
      if (bw.status === 'fulfilled') setBowlingRows(bw.value)
      if (f.status === 'fulfilled') setFieldingRows(f.value)
    }).finally(() => setLoading(false))
  }, [orgId, selectedSeason, selectedGradeName, battingSort, bowlingSort, fieldingSort, effectiveMinRuns, effectiveMinOvers, effectiveMinWickets])

  if (clubLoading) return <PbSpinner message="Loading club data…" />

  const currentSeason = seasons?.find(s => s.id === selectedSeason)
  const seasonLabel = currentSeason?.name || 'ALL SEASONS'

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1300px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <PageHeader
          eyebrow={`CLUB LEADERBOARD · ${seasonLabel.toUpperCase()}`}
          title="The ladder."
          meta={[<span key="s">All categories. All grades.</span>]}
        />

        {/* Season + grade filters */}
        <div className="mb-5 flex flex-wrap gap-3 items-center">
          <SeasonSelector
            seasons={seasons}
            grades={[]}
            selectedSeason={selectedSeason}
            setSelectedSeason={setSelectedSeason}
            selectedGrade={null}
            setSelectedGrade={() => {}}
          />
          {orgGrades.length > 0 && (
            <div className="flex items-center gap-2">
              <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase whitespace-nowrap">Grade</label>
              <select
                value={selectedGradeName || ''}
                onChange={e => setSelectedGradeName(e.target.value || null)}
                className="bg-pb-surface border pb-hairline text-pb-text text-sm rounded px-3 py-1.5 focus:outline-none focus:border-pb-accent"
              >
                <option value="">All grades</option>
                {orgGrades.map(g => (
                  <option key={g.name} value={g.name}>{g.name}</option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* Main tab: batting / bowling / fielding */}
        <div className="flex flex-wrap gap-1 pb-hairline-b mb-4">
          {MAIN_TABS.map(t => (
            <button key={t.key} onClick={() => setMainTab(t.key)}
              className={`relative px-3.5 py-2.5 text-[11px] font-mono font-semibold tracking-wide3 transition ${
                mainTab === t.key ? 'text-pb-text' : 'text-pb-faint hover:text-pb-dim'
              }`}>
              {t.label}
              {mainTab === t.key && <span className="absolute left-2 right-2 -bottom-px h-[2px]" style={{ background: 'var(--pb-accent)' }} />}
            </button>
          ))}
        </div>

        {/* Sort sub-tabs */}
        {mainTab === 'batting' && (
          <div className="flex flex-wrap gap-1 mb-4 pb-hairline-b">
            {BATTING_SORTS.map(s => (
              <SortBtn key={s.key} label={s.label} active={battingSort === s.key} onClick={() => setBattingSort(s.key)} />
            ))}
          </div>
        )}
        {mainTab === 'batting' && battingSort === 'average' && (
          <MinFilterInput label="Min. runs" value={minRuns} onChange={setMinRuns} />
        )}
        {mainTab === 'bowling' && (
          <div className="flex flex-wrap gap-1 mb-4 pb-hairline-b">
            {BOWLING_SORTS.map(s => (
              <SortBtn key={s.key} label={s.label} active={bowlingSort === s.key} onClick={() => setBowlingSort(s.key)} />
            ))}
          </div>
        )}
        {mainTab === 'bowling' && bowlingSort === 'economy' && (
          <MinFilterInput label="Min. overs" value={minOvers} onChange={setMinOvers} />
        )}
        {mainTab === 'bowling' && bowlingSort === 'average' && (
          <MinFilterInput label="Min. wickets" value={minWickets} onChange={setMinWickets} />
        )}
        {mainTab === 'fielding' && (
          <div className="flex flex-wrap gap-1 mb-4 pb-hairline-b">
            {FIELDING_SORTS.map(s => (
              <SortBtn key={s.key} label={s.label} active={fieldingSort === s.key} onClick={() => setFieldingSort(s.key)} />
            ))}
          </div>
        )}

        {/* Table */}
        {loading ? <PbSpinner /> : (
          <>
            {mainTab === 'batting' && (
              battingRows.length === 0
                ? <p className="text-pb-faint text-sm py-8 text-center">No batting data yet.</p>
                : <BattingTable rows={battingRows} sortBy={battingSort} fmt={fmt} />
            )}
            {mainTab === 'bowling' && (
              bowlingRows.length === 0
                ? <p className="text-pb-faint text-sm py-8 text-center">No bowling data yet.</p>
                : <BowlingTable rows={bowlingRows} sortBy={bowlingSort} fmt={fmt} />
            )}
            {mainTab === 'fielding' && (
              fieldingRows.length === 0
                ? <p className="text-pb-faint text-sm py-8 text-center">No fielding data yet.</p>
                : <FieldingTable rows={fieldingRows} sortBy={fieldingSort} fmt={fmt} />
            )}
          </>
        )}
      </main>
    </div>
  )
}
