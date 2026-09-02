import { useParams, useSearchParams, Link } from 'react-router-dom'
import { useState, useEffect, useRef, Fragment } from 'react'
import { useClubData } from '../hooks/useClubData'
import { useClub } from '../hooks/useClub'
import { useClubTheme } from '../hooks/useClubTheme'
import { usePageMeta } from '../hooks/usePageMeta'
import { useGradeFilters } from '../hooks/useGradeCategories'
import { api } from '../lib/api'
import ClubInactive from './ClubInactive'
import ClubPinGate from './ClubPinGate'
import SeasonSelector from '../components/SeasonSelector'
import {
  Label, Card, PageHeader, PbSpinner,
} from '../lib/presskit'
import { useNameFormat } from '../lib/nameFormat'
import { fmt2, fmtCount, formatSeason } from '../lib/cricketFormat'
import { RateMark, RateFootnote, RateInfo } from '../components/RateCoverage'

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
  { key: 'total_wickets',        label: 'WICKETS' },
  { key: 'economy',              label: 'ECONOMY' },
  { key: 'average',              label: 'AVERAGE' },
  { key: 'best_figures_wickets', label: 'BEST FIGURES' },
  { key: 'five_fors',            label: 'FIVE-FORS' },
  { key: 'total_maidens',        label: 'MAIDENS' },
]

const FIELDING_SORTS = [
  { key: 'total_catches_non_wk', label: 'CATCHES' },
  { key: 'total_catches_wk',  label: 'WK CATCHES' },
  { key: 'total_run_outs',    label: 'RUN OUTS' },
  { key: 'total_stumpings',   label: 'STUMPINGS' },
]

const MAIN_TABS = [
  { key: 'batting',  label: 'BATTING' },
  { key: 'bowling',  label: 'BOWLING' },
  { key: 'fielding', label: 'FIELDING' },
  { key: 'sirs',     label: 'SIRS' },
]

const SIRS_TABS = [
  { key: 'centuries',       label: 'CENTURIES',    countKey: 'century_count', threshold: '100+ runs' },
  { key: 'bowling-innings', label: '7-FORS',       countKey: 'haul_count',   threshold: '7+ wickets in an innings' },
  { key: 'bowling-match',   label: '10-WKT MATCH', countKey: 'haul_count',   threshold: '10+ wickets in a match' },
]

function formatSirsDate(dateStr) {
  if (!dateStr) return '—'
  const d = new Date(dateStr + 'T00:00:00')
  return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: '2-digit' })
}

function SirsTable({ rows, sirsType, fmt = n => n }) {
  const [expanded, setExpanded] = useState(new Set())
  const tab = SIRS_TABS.find(t => t.key === sirsType)
  const countKey = tab?.countKey || 'century_count'
  const isBatting = sirsType === 'centuries'

  const toggle = id => setExpanded(prev => {
    const next = new Set(prev)
    if (next.has(id)) { next.delete(id) } else { next.add(id) }
    return next
  })

  return (
    <Card pad="p-0">
      <div className="overflow-x-auto pb-scroll">
        <table className="w-full min-w-[460px] text-[14px]">
          <thead>
            <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left bg-pb-surface2/40">
              <th className="font-medium py-3 pl-5 w-10">#</th>
              <th className="font-medium py-3">PLAYER</th>
              <th className="font-medium py-3 text-right pr-3" style={{ color: 'var(--pb-accent)' }}>
                {tab?.label || 'COUNT'}
              </th>
              <th className="py-3 pr-4 w-8" />
            </tr>
          </thead>
          <tbody>
            {rows.map((p, i) => (
              <Fragment key={p.player_id}>
                <tr
                  className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2 cursor-pointer`}
                  onClick={() => toggle(p.player_id)}
                >
                  <td className="py-3 pl-5 font-mono text-pb-faint">{String(i + 1).padStart(2, '0')}</td>
                  <td className="py-3">
                    <Link
                      to={`/players/${p.player_id}`}
                      className="text-pb-text font-semibold hover:text-pb-accent"
                      onClick={e => e.stopPropagation()}
                    >
                      {fmt(p.name)}
                    </Link>
                  </td>
                  <td className="py-3 pr-3 text-right">
                    <span className="font-mono text-[15px] font-bold" style={{ color: 'var(--pb-accent)' }}>
                      {p[countKey] ?? '—'}
                    </span>
                  </td>
                  <td className="py-3 pr-4 text-right font-mono text-pb-faint text-[10px]">
                    {expanded.has(p.player_id) ? '▲' : '▼'}
                  </td>
                </tr>
                {expanded.has(p.player_id) && (
                  <tr>
                    <td colSpan={4} className="pb-4 px-5 bg-pb-surface2/20">
                      <table className="w-full text-[12px] font-mono">
                        <thead>
                          <tr className="text-pb-faint text-[10px] tracking-wide3">
                            <th className="py-1.5 text-right pr-5 w-16">{isBatting ? 'RUNS' : 'FIGURES'}</th>
                            <th className="py-1.5 text-left pr-4">GRADE</th>
                            <th className="py-1.5 text-left pr-4">SEASON</th>
                            <th className="py-1.5 text-left">DATE</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(p.performances || []).map((perf, j) => (
                            <tr key={j} className={j ? 'pb-hairline-t' : ''}>
                              <td className="py-1 pr-5 text-right font-bold" style={{ color: 'var(--pb-accent)' }}>
                                {isBatting
                                  ? `${perf.runs}${perf.not_out ? '*' : ''}`
                                  : `${perf.wickets}/${perf.runs}`}
                              </td>
                              <td className="py-1 pr-4 text-pb-dim">{perf.grade || '—'}</td>
                              <td className="py-1 pr-4 text-pb-dim">{formatSeason(perf.season) || '—'}</td>
                              <td className="py-1 text-pb-dim">{formatSirsDate(perf.date)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

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
  if (sortBy === 'strike_rate') return ['M', 'SR', 'RUNS', 'INN', 'AVG']
  if (sortBy === 'high_score')  return ['M', 'HS', 'RUNS', 'AVG']
  if (sortBy === 'fifties')     return ['M', '50s', 'RUNS', 'AVG']
  if (sortBy === 'hundreds')    return ['M', '100s', 'RUNS', 'AVG']
  if (sortBy === 'total_sixes') return ['M', '6s', 'RUNS']
  if (sortBy === 'total_fours') return ['M', '4s', 'RUNS']
  if (sortBy === 'ducks')       return ['M', 'DUCKS', 'INN']
  return base
}

/**
 * How many ball-counted innings (or overs-carrying spells) a player needs
 * before their rate is ranked here.
 *
 * Counted on the innings that could answer the question, never on innings
 * played: ten innings with three ball counts is a three-innings strike rate,
 * and letting that clear a ten-innings bar is what the bar exists to stop.
 *
 * "Club default" is the absence of a pick rather than a number of its own, so
 * it sends nothing and the club's own setting applies.
 */
function RateMinPills({ label, value, onChange, unit = 'innings' }) {
  const OPTIONS = [
    { v: null, label: 'Club default' },
    { v: 0, label: 'Any' },
    { v: 3, label: '3+' },
    { v: 5, label: '5+' },
    { v: 10, label: '10+' },
    { v: 20, label: '20+' },
  ]
  return (
    <div className="flex flex-wrap items-center gap-2 px-1 py-2 mb-3">
      <span className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">{label}</span>
      <div className="flex flex-wrap gap-1">
        {OPTIONS.map(o => (
          <button
            key={String(o.v)}
            type="button"
            onClick={() => onChange(o.v)}
            aria-pressed={value === o.v}
            className={`px-2 py-1 rounded font-mono text-[11px] border transition-colors ${
              value === o.v
                ? 'border-pb-accent text-pb-accent'
                : 'border-pb-hairline text-pb-dim hover:text-pb-text'
            }`}
            style={value === o.v ? { background: 'color-mix(in srgb, var(--pb-accent) 10%, transparent)' } : {}}
          >
            {o.label}
          </button>
        ))}
      </div>
      <RateInfo unit={unit} />
    </div>
  )
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
                  style={c === primaryLabel || c === 'SR' || c === 'RUNS' || c === 'AVG' || c === 'INN' || c === 'HS' || c === '50s' || c === '100s' || c === '6s' || c === '4s' || c === 'DUCKS' || c === 'M'
                    ? (c === primaryLabel || (c === 'RUNS' && sortBy === 'total_runs') || (c === 'AVG' && sortBy === 'average') || (c === 'HS' && sortBy === 'high_score') || (c === '50s' && sortBy === 'fifties') || (c === '100s' && sortBy === 'hundreds') || (c === '6s' && sortBy === 'total_sixes') || (c === '4s' && sortBy === 'total_fours') || (c === 'DUCKS' && sortBy === 'ducks') || (c === 'SR' && sortBy === 'strike_rate'))
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
                  const isPrimary = (c === 'RUNS' && sortBy === 'total_runs') || (c === 'AVG' && sortBy === 'average') || (c === 'HS' && sortBy === 'high_score') || (c === '50s' && sortBy === 'fifties') || (c === '100s' && sortBy === 'hundreds') || (c === '6s' && sortBy === 'total_sixes') || (c === '4s' && sortBy === 'total_fours') || (c === 'DUCKS' && sortBy === 'ducks') || (c === 'SR' && sortBy === 'strike_rate')
                  if (c === 'M')    val = p.games != null ? fmtCount(p.games) : '—'
                  else if (c === 'RUNS')  val = p.total_runs != null ? fmtCount(p.total_runs) : '—'
                  else if (c === 'INN')   val = p.innings ?? '—'
                  else if (c === 'AVG')   val = fmt2(p.average)
                  else if (c === 'SR')    val = <>{fmt2(p.strike_rate)}<RateMark coverage={p.strike_rate_coverage} /></>
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
      <RateFootnote rows={rows} when={cols.includes('SR')} />
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
                      ? (p.best_bowling_figures ? p.best_bowling_figures.replace('-', '/') : p.best_figures_wickets != null ? `${fmtCount(p.best_figures_wickets)} wickets` : '—')
                      : sortBy === 'economy' ? <>{fmt2(p.economy)}<RateMark coverage={p.economy_coverage} unit="spells" /></>
                      : sortBy === 'average' ? fmt2(p.average)
                      : sortBy === 'total_wickets' ? (p.total_wickets != null ? fmtCount(p.total_wickets) : '—')
                      : (p[sortBy] ?? '—')}
                  </span>
                </td>
                {sortBy !== 'total_wickets' && (
                  <td className="py-3 pr-3 font-mono text-pb-text text-right">{p.total_wickets != null ? fmtCount(p.total_wickets) : '—'}</td>
                )}
                <td className="py-3 pr-3 font-mono text-pb-dim text-right">{fmt2(p.average)}</td>
                <td className="py-3 pr-3 font-mono text-pb-dim text-right">{fmt2(p.economy)}<RateMark coverage={p.economy_coverage} unit="spells" /></td>
                <td className="py-3 pr-5 font-mono text-pb-dim text-right">
                  {p.best_bowling_figures ? p.best_bowling_figures.replace('-', '/') : p.best_figures_wickets != null ? `${fmtCount(p.best_figures_wickets)} wickets` : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <RateFootnote rows={rows} field="economy_coverage" unit="spells" />
    </Card>
  )
}

function FieldingTable({ rows, sortBy, fmt = n => n }) {
  const primaryLabel = FIELDING_SORTS.find(s => s.key === sortBy)?.label || 'CATCHES'
  const primaryKey = sortBy || 'total_catches_non_wk'

  return (
    <Card pad="p-0">
      <div className="overflow-x-auto pb-scroll">
        <table className="w-full min-w-[500px] text-[14px]">
          <thead>
            <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left bg-pb-surface2/40">
              <th className="font-medium py-3 pl-5 w-10">#</th>
              <th className="font-medium py-3">PLAYER</th>
              <th className="font-medium py-3 text-right pr-3">M</th>
              <th className="font-medium py-3 text-right pr-3" style={{ color: 'var(--pb-accent)' }}>{primaryLabel}</th>
              {sortBy !== 'total_catches_non_wk' && <th className="font-medium py-3 text-right pr-3">CATCHES</th>}
              {sortBy !== 'total_catches_wk'     && <th className="font-medium py-3 text-right pr-3">WK CT</th>}
              {sortBy !== 'total_run_outs'   && <th className="font-medium py-3 text-right pr-3">RUN OUTS</th>}
              {sortBy !== 'total_stumpings'  && <th className="font-medium py-3 pr-5 text-right">STUMPINGS</th>}
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
                {sortBy !== 'total_catches_non_wk' && <td className="py-3 pr-3 font-mono text-pb-dim text-right">{p.total_catches_non_wk ?? '—'}</td>}
                {sortBy !== 'total_catches_wk'     && <td className="py-3 pr-3 font-mono text-pb-dim text-right">{p.total_catches_wk ?? '—'}</td>}
                {sortBy !== 'total_run_outs'   && <td className="py-3 pr-3 font-mono text-pb-dim text-right">{p.total_run_outs ?? '—'}</td>}
                {sortBy !== 'total_stumpings'  && <td className="py-3 pr-5 font-mono text-pb-dim text-right">{p.total_stumpings ?? '—'}</td>}
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
  const { club, orgId, inactive, notFound, locked, unlock, requestAccess } = useClub(clubSlug)
  useClubTheme(club)
  const fmt = useNameFormat(club)
  usePageMeta({
    title: club?.name ? `${club.name} Leaderboard — BetterStats` : null,
    description: club?.name ? `Top batting, bowling, and fielding statistics for ${club.name}.` : null,
    image: club?.logo_url || null,
  })

  const { org, seasons, selectedSeason, setSelectedSeason, loading: clubLoading } = useClubData(orgId)

  const [orgGrades, setOrgGrades] = useState([])
  const [selectedGradeName, setSelectedGradeName] = useState(null)
  const [finalsOnly, setFinalsOnly] = useState(false)
  const [captainOnly, setCaptainOnly] = useState(false)
  const [gender, setGender] = useState(null)
  const [overseas, setOverseas] = useState(null)
  // The same two pick-one rows the club dashboard uses — grade type and match
  // type — rather than the old additive Include row. One control across every
  // stats screen, and Match Type is only answerable here now that it is read
  // per fixture.
  const {
    available: availableCategories, availableFormats, defaultCategories,
    gradeType, setGradeType, matchFormat, setMatchFormat,
    categoriesParam, formatsParam, competitionsParam,
    competition, setCompetition, availableCompetitions,
  } = useGradeFilters(orgId)

  const [mainTab, setMainTab] = useState('batting')
  const [battingSort, setBattingSort] = useState('total_runs')
  const [bowlingSort, setBowlingSort] = useState('total_wickets')
  const [fieldingSort, setFieldingSort] = useState('total_catches_non_wk')

  const [minRuns, setMinRuns] = useState(500)
  const [minOvers, setMinOvers] = useState(100)
  const [minWickets, setMinWickets] = useState(50)
  // null means "whatever the club set", which is what omitting the param asks
  // for. 0 is a real answer — it is how a reader switches the bar off — so this
  // is never collapsed to a falsy check.
  const [minRateInnings, setMinRateInnings] = useState(null)
  const [minRateSpells, setMinRateSpells] = useState(null)

  const [battingRows, setBattingRows] = useState([])
  const [bowlingRows, setBowlingRows] = useState([])
  const [fieldingRows, setFieldingRows] = useState([])
  const [loading, setLoading] = useState(true)

  const [sirsTab, setSirsTab] = useState('centuries')
  const [centuriesRows, setCenturiesRows] = useState([])
  const [bowlingInningsRows, setBowlingInningsRows] = useState([])
  const [bowlingMatchRows, setBowlingMatchRows] = useState([])
  const [sirsLoading, setSirsLoading] = useState(false)

  useEffect(() => {
    if (!orgId) return
    api.getOrgGrades(orgId, selectedSeason)
      .then(grades => {
        setOrgGrades(grades)
        setSelectedGradeName(prev => (prev && grades.some(g => g.name === prev) ? prev : null))
      })
      .catch(() => setOrgGrades([]))
  }, [orgId, selectedSeason])

  // Deep-link support: ?season=<id>&grade=<gradeName> (e.g. from the Ladders page).
  const [searchParams] = useSearchParams()
  const urlSeasonApplied = useRef(false)
  const urlGradeApplied = useRef(false)
  useEffect(() => {
    if (urlSeasonApplied.current || seasons.length === 0) return
    const s = searchParams.get('season')
    if (s && seasons.some(x => x.id === s)) setSelectedSeason(s)
    urlSeasonApplied.current = true
  }, [seasons, searchParams, setSelectedSeason])
  useEffect(() => {
    if (urlGradeApplied.current) return
    const g = searchParams.get('grade')
    if (g && orgGrades.some(x => x.name === g)) {
      setSelectedGradeName(g)
      urlGradeApplied.current = true
    }
  }, [orgGrades, searchParams])

  const effectiveMinRuns = battingSort === 'average' ? minRuns : 0
  const effectiveMinRateInnings = battingSort === 'strike_rate' ? minRateInnings : null
  const effectiveMinRateSpells = bowlingSort === 'economy' ? minRateSpells : null
  const effectiveMinOvers = bowlingSort === 'economy' ? minOvers : 0
  const effectiveMinWickets = bowlingSort === 'average' ? minWickets : 0

  useEffect(() => {
    if (!orgId) return
    setLoading(true)
    Promise.allSettled([
      api.battingLeaderboard(orgId, { seasonId: selectedSeason, gradeName: selectedGradeName, sortBy: battingSort, limit: 30, minRuns: effectiveMinRuns, minRateInnings: effectiveMinRateInnings, finalsOnly, captainOnly, gender, overseas, categories: categoriesParam, formats: formatsParam, competitions: competitionsParam }),
      api.bowlingLeaderboard(orgId, { seasonId: selectedSeason, gradeName: selectedGradeName, sortBy: bowlingSort, limit: 30, minOvers: effectiveMinOvers, minWickets: effectiveMinWickets, minRateSpells: effectiveMinRateSpells, finalsOnly, captainOnly, gender, overseas, categories: categoriesParam, formats: formatsParam, competitions: competitionsParam }),
      api.fieldingLeaderboard(orgId, { seasonId: selectedSeason, gradeName: selectedGradeName, sortBy: fieldingSort, limit: 30, finalsOnly, captainOnly, gender, overseas, categories: categoriesParam, formats: formatsParam, competitions: competitionsParam }),
    ]).then(([b, bw, f]) => {
      if (b.status === 'fulfilled') setBattingRows(b.value)
      if (bw.status === 'fulfilled') setBowlingRows(bw.value)
      if (f.status === 'fulfilled') setFieldingRows(f.value)
    }).finally(() => setLoading(false))
  }, [orgId, selectedSeason, selectedGradeName, battingSort, bowlingSort, fieldingSort, effectiveMinRuns, effectiveMinOvers, effectiveMinWickets, effectiveMinRateInnings, effectiveMinRateSpells, finalsOnly, captainOnly, gender, overseas, categoriesParam, formatsParam, competitionsParam])

  useEffect(() => {
    if (!orgId || mainTab !== 'sirs') return
    setSirsLoading(true)
    Promise.allSettled([
      api.sirsLeaderboard(orgId, 'batting', { seasonId: selectedSeason, gradeName: selectedGradeName, finalsOnly, captainOnly, gender, overseas, categories: categoriesParam, formats: formatsParam, competitions: competitionsParam }),
      api.sirsLeaderboard(orgId, 'bowling-innings', { seasonId: selectedSeason, gradeName: selectedGradeName, finalsOnly, captainOnly, gender, overseas, categories: categoriesParam, formats: formatsParam, competitions: competitionsParam }),
      api.sirsLeaderboard(orgId, 'bowling-match', { seasonId: selectedSeason, gradeName: selectedGradeName, finalsOnly, captainOnly, gender, overseas, categories: categoriesParam, formats: formatsParam, competitions: competitionsParam }),
    ]).then(([sc, sbi, sbm]) => {
      if (sc.status === 'fulfilled') setCenturiesRows(sc.value)
      if (sbi.status === 'fulfilled') setBowlingInningsRows(sbi.value)
      if (sbm.status === 'fulfilled') setBowlingMatchRows(sbm.value)
    }).finally(() => setSirsLoading(false))
  }, [orgId, selectedSeason, selectedGradeName, finalsOnly, captainOnly, gender, overseas, categoriesParam, formatsParam, mainTab])

  if (locked) return <ClubPinGate slug={clubSlug} lockInfo={locked} unlock={unlock} requestAccess={requestAccess} />
  if (inactive) return <ClubInactive slug={clubSlug} />
  if (notFound) return <ClubInactive variant="notfound" slug={clubSlug} />
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
            finalsOnly={finalsOnly}
            setFinalsOnly={setFinalsOnly}
            captainOnly={captainOnly}
            setCaptainOnly={setCaptainOnly}
            gender={gender}
            setGender={setGender}
            overseas={overseas}
            setOverseas={setOverseas}
            showOverseasFilter
            gradeType={gradeType}
            setGradeType={setGradeType}
            matchFormat={matchFormat}
            setMatchFormat={setMatchFormat}
            competition={competition}
            setCompetition={setCompetition}
            availableCompetitions={availableCompetitions}
            availableCategories={availableCategories}
            availableFormats={availableFormats}
            defaultCategories={defaultCategories}
            showCompetitionFilter
            showGradeTypeFilter
            showMatchFormatFilter
          />
          {orgGrades.length > 0 && (
            <div className="flex items-center gap-2">
              <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase whitespace-nowrap hidden sm:block">Grade</label>
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

        {/* Main tab: batting / bowling / fielding / sirs */}
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
        {mainTab === 'batting' && battingSort === 'strike_rate' && (
          <RateMinPills
            label="Min. innings with balls faced"
            value={minRateInnings}
            onChange={setMinRateInnings}
          />
        )}
        {mainTab === 'bowling' && (
          <div className="flex flex-wrap gap-1 mb-4 pb-hairline-b">
            {BOWLING_SORTS.map(s => (
              <SortBtn key={s.key} label={s.label} active={bowlingSort === s.key} onClick={() => setBowlingSort(s.key)} />
            ))}
          </div>
        )}
        {mainTab === 'bowling' && bowlingSort === 'economy' && (
          <>
            <MinFilterInput label="Min. overs" value={minOvers} onChange={setMinOvers} />
            <RateMinPills
              label="Min. spells with overs recorded"
              value={minRateSpells}
              onChange={setMinRateSpells}
              unit="spells"
            />
          </>
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
        {mainTab === 'sirs' && (
          <div className="flex flex-wrap gap-1 mb-4 pb-hairline-b">
            {SIRS_TABS.map(t => (
              <SortBtn key={t.key} label={t.label} active={sirsTab === t.key} onClick={() => setSirsTab(t.key)} />
            ))}
          </div>
        )}

        {/* Table */}
        {mainTab !== 'sirs' && (loading ? <PbSpinner /> : (
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
        ))}
        {mainTab === 'sirs' && (
          sirsLoading ? <PbSpinner /> : (() => {
            const sirsRows = sirsTab === 'centuries' ? centuriesRows : sirsTab === 'bowling-innings' ? bowlingInningsRows : bowlingMatchRows
            const threshold = SIRS_TABS.find(t => t.key === sirsTab)?.threshold
            return sirsRows.length === 0
              ? <p className="text-pb-faint text-sm py-8 text-center">No data yet.</p>
              : (
                <>
                  {threshold && (
                    <p className="text-pb-faint font-mono text-[10px] tracking-wide3 uppercase mb-3">{threshold} — click a row to expand</p>
                  )}
                  <SirsTable rows={sirsRows} sirsType={sirsTab} fmt={fmt} />
                </>
              )
          })()
        )}
      </main>
    </div>
  )
}
