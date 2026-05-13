import { useParams, Link } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { useClubData } from '../hooks/useClubData'
import { useClub } from '../hooks/useClub'
import { useClubTheme } from '../hooks/useClubTheme'
import { api } from '../lib/api'
import ClubInactive from './ClubInactive'
import SeasonSelector from '../components/SeasonSelector'
import {
  AnimatedNum, Label, Card, Btn, PageHeader, PbSpinner, FilterGroup,
} from '../lib/presskit'

const BATTING_SORTS = [
  { key: 'total_runs',    label: 'MOST RUNS' },
  { key: 'average',       label: 'AVERAGE' },
  { key: 'strike_rate',   label: 'STRIKE RATE' },
  { key: 'high_score',    label: 'HIGH SCORE' },
  { key: 'fifties',       label: 'FIFTIES' },
  { key: 'hundreds',      label: 'CENTURIES' },
  { key: 'total_sixes',   label: 'SIXES' },
  { key: 'total_fours',   label: 'FOURS' },
  { key: 'ducks',         label: 'DUCKS' },
]

const BOWLING_SORTS = [
  { key: 'total_wickets',         label: 'WICKETS' },
  { key: 'economy',               label: 'ECONOMY' },
  { key: 'average',               label: 'AVERAGE' },
  { key: 'best_figures_wickets',  label: 'BEST SPELL' },
  { key: 'five_fors',             label: 'FIVE-FORS' },
  { key: 'total_maidens',         label: 'MAIDENS' },
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

function BattingTable({ rows, sortBy }) {
  const primaryLabel = BATTING_SORTS.find(s => s.key === sortBy)?.label || 'VALUE'
  const primaryKey = sortBy || 'total_runs'
  const isInverted = sortBy === 'ducks'

  return (
    <Card pad="p-0">
      <div className="overflow-x-auto pb-scroll">
        <table className="w-full min-w-[700px] text-[14px]">
          <thead>
            <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left bg-pb-surface2/40">
              <th className="font-medium py-3 pl-5 w-10">#</th>
              <th className="font-medium py-3">PLAYER</th>
              <th className="font-medium py-3 text-right" style={{ color: 'var(--pb-accent)' }}>{primaryLabel}</th>
              {sortBy !== 'total_runs' && <th className="font-medium py-3 text-right">RUNS</th>}
              <th className="font-medium py-3 text-right">INN</th>
              <th className="font-medium py-3 text-right">AVG</th>
              <th className="font-medium py-3 text-right">HS</th>
              <th className="font-medium py-3 pr-5 text-right hidden sm:table-cell">SR</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p, i) => (
              <tr key={p.player_id} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                <td className="py-3 pl-5 font-mono text-pb-faint">{String(i + 1).padStart(2, '0')}</td>
                <td className="py-3">
                  <Link to={`/players/${p.player_id}`} className="text-pb-text font-semibold hover:text-pb-accent">{p.name}</Link>
                  {p.hundreds > 0 && <span className="ml-2 font-mono text-[10px] text-pb-faint">{p.hundreds}×💯</span>}
                </td>
                <td className="py-3 text-right">
                  <span className="font-mono text-[15px] font-bold pb-num" style={{ color: 'var(--pb-accent)' }}>
                    {p[primaryKey] ?? '—'}
                  </span>
                </td>
                {sortBy !== 'total_runs' && (
                  <td className="py-3 font-mono text-pb-text text-right">{p.total_runs ?? '—'}</td>
                )}
                <td className="py-3 font-mono text-pb-dim text-right">{p.batting_innings ?? '—'}</td>
                <td className="py-3 font-mono text-pb-dim text-right">{p.average ?? '—'}</td>
                <td className="py-3 font-mono text-pb-dim text-right">{p.high_score ?? '—'}</td>
                <td className="py-3 pr-5 font-mono text-pb-dim text-right hidden sm:table-cell">{p.strike_rate ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function BowlingTable({ rows, sortBy }) {
  const primaryLabel = BOWLING_SORTS.find(s => s.key === sortBy)?.label || 'WICKETS'
  const primaryKey = sortBy || 'total_wickets'

  return (
    <Card pad="p-0">
      <div className="overflow-x-auto pb-scroll">
        <table className="w-full min-w-[640px] text-[14px]">
          <thead>
            <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left bg-pb-surface2/40">
              <th className="font-medium py-3 pl-5 w-10">#</th>
              <th className="font-medium py-3">PLAYER</th>
              <th className="font-medium py-3 text-right" style={{ color: 'var(--pb-accent)' }}>{primaryLabel}</th>
              {sortBy !== 'total_wickets' && <th className="font-medium py-3 text-right">WKTS</th>}
              <th className="font-medium py-3 text-right">AVG</th>
              <th className="font-medium py-3 text-right">ECON</th>
              <th className="font-medium py-3 pr-5 text-right">BEST</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p, i) => (
              <tr key={p.player_id} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                <td className="py-3 pl-5 font-mono text-pb-faint">{String(i + 1).padStart(2, '0')}</td>
                <td className="py-3">
                  <Link to={`/players/${p.player_id}`} className="text-pb-text font-semibold hover:text-pb-accent">{p.name}</Link>
                  {p.five_fors > 0 && <span className="ml-2 font-mono text-[10px] text-pb-faint">{p.five_fors}×5W</span>}
                </td>
                <td className="py-3 text-right">
                  <span className="font-mono text-[15px] font-bold pb-num" style={{ color: 'var(--pb-accent)' }}>
                    {primaryKey === 'best_figures_wickets'
                      ? (p.best_figures_wickets != null ? `${p.best_figures_wickets}/${p.best_figures_runs ?? '?'}` : '—')
                      : (p[primaryKey] ?? '—')}
                  </span>
                </td>
                {sortBy !== 'total_wickets' && (
                  <td className="py-3 font-mono text-pb-text text-right">{p.total_wickets ?? '—'}</td>
                )}
                <td className="py-3 font-mono text-pb-dim text-right">{p.average ?? '—'}</td>
                <td className="py-3 font-mono text-pb-dim text-right">{p.economy ?? '—'}</td>
                <td className="py-3 pr-5 font-mono text-pb-dim text-right">
                  {p.best_figures_wickets != null ? `${p.best_figures_wickets}/${p.best_figures_runs ?? '?'}` : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function FieldingTable({ rows, sortBy }) {
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
              <th className="font-medium py-3 text-right" style={{ color: 'var(--pb-accent)' }}>{primaryLabel}</th>
              <th className="font-medium py-3 text-right">CATCHES</th>
              <th className="font-medium py-3 text-right">RUN OUTS</th>
              <th className="font-medium py-3 pr-5 text-right">STUMPINGS</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p, i) => (
              <tr key={p.player_id} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                <td className="py-3 pl-5 font-mono text-pb-faint">{String(i + 1).padStart(2, '0')}</td>
                <td className="py-3">
                  <Link to={`/players/${p.player_id}`} className="text-pb-text font-semibold hover:text-pb-accent">{p.name}</Link>
                </td>
                <td className="py-3 text-right">
                  <span className="font-mono text-[15px] font-bold pb-num" style={{ color: 'var(--pb-accent)' }}>
                    {p[primaryKey] ?? '—'}
                  </span>
                </td>
                <td className="py-3 font-mono text-pb-dim text-right">{p.total_catches ?? '—'}</td>
                <td className="py-3 font-mono text-pb-dim text-right">{p.total_run_outs ?? '—'}</td>
                <td className="py-3 pr-5 font-mono text-pb-dim text-right">{p.total_stumpings ?? '—'}</td>
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

  if (inactive) return <ClubInactive />

  const { org, seasons, grades, selectedSeason, setSelectedSeason, selectedGrade, setSelectedGrade, loading: clubLoading } = useClubData(orgId)

  const [mainTab, setMainTab] = useState('batting')
  const [battingSort, setBattingSort] = useState('total_runs')
  const [bowlingSort, setBowlingSort] = useState('total_wickets')
  const [fieldingSort, setFieldingSort] = useState('total_catches')

  const [battingRows, setBattingRows] = useState([])
  const [bowlingRows, setBowlingRows] = useState([])
  const [fieldingRows, setFieldingRows] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!orgId) return
    setLoading(true)
    Promise.allSettled([
      api.battingLeaderboard(orgId, { seasonId: selectedSeason, gradeId: selectedGrade, sortBy: battingSort, limit: 30 }),
      api.bowlingLeaderboard(orgId, { seasonId: selectedSeason, gradeId: selectedGrade, sortBy: bowlingSort, limit: 30 }),
      api.fieldingLeaderboard(orgId, { seasonId: selectedSeason, gradeId: selectedGrade, limit: 30 }),
    ]).then(([b, bw, f]) => {
      if (b.status === 'fulfilled') setBattingRows(b.value)
      if (bw.status === 'fulfilled') setBowlingRows(bw.value)
      if (f.status === 'fulfilled') setFieldingRows(f.value)
    }).finally(() => setLoading(false))
  }, [orgId, selectedSeason, selectedGrade, battingSort, bowlingSort])

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

        {/* Season filter */}
        <div className="mb-5">
          <SeasonSelector
            seasons={seasons}
            grades={grades}
            selectedSeason={selectedSeason}
            setSelectedSeason={setSelectedSeason}
            selectedGrade={selectedGrade}
            setSelectedGrade={setSelectedGrade}
          />
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
        {mainTab === 'bowling' && (
          <div className="flex flex-wrap gap-1 mb-4 pb-hairline-b">
            {BOWLING_SORTS.map(s => (
              <SortBtn key={s.key} label={s.label} active={bowlingSort === s.key} onClick={() => setBowlingSort(s.key)} />
            ))}
          </div>
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
                : <BattingTable rows={battingRows} sortBy={battingSort} />
            )}
            {mainTab === 'bowling' && (
              bowlingRows.length === 0
                ? <p className="text-pb-faint text-sm py-8 text-center">No bowling data yet.</p>
                : <BowlingTable rows={bowlingRows} sortBy={bowlingSort} />
            )}
            {mainTab === 'fielding' && (
              fieldingRows.length === 0
                ? <p className="text-pb-faint text-sm py-8 text-center">No fielding data yet.</p>
                : <FieldingTable rows={fieldingRows} sortBy={fieldingSort} />
            )}
          </>
        )}
      </main>
    </div>
  )
}
