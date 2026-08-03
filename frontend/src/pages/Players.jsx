import { useParams, Link } from 'react-router-dom'
import { useState, useEffect, useMemo } from 'react'
import { useClubData } from '../hooks/useClubData'
import { useClub } from '../hooks/useClub'
import { useClubTheme } from '../hooks/useClubTheme'
import { api } from '../lib/api'
import ClubInactive from './ClubInactive'
import ClubPinGate from './ClubPinGate'
import SeasonSelector from '../components/SeasonSelector'
import { PageHeader, PbSpinner, Card } from '../lib/presskit'
import { useNameFormat, nameMatchesSearch } from '../lib/nameFormat'
import { fmt2, fmtCount } from '../lib/cricketFormat'

function PlayerStat({ label, value, accent }) {
  const display = value ?? '—'
  return (
    <div className="flex flex-col items-center">
      <span
        className={`font-mono font-bold leading-tight pb-num ${accent ? '' : 'text-pb-dim'}`}
        style={accent ? { color: 'var(--pb-accent)' } : undefined}
      >
        {display}
      </span>
      <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest uppercase">{label}</span>
    </div>
  )
}

export default function Players() {
  const { clubSlug } = useParams()
  const { club, orgId, inactive, notFound, locked, unlock, requestAccess } = useClub(clubSlug)
  useClubTheme(club)
  const fmt = useNameFormat(club)
  const { org, seasons, grades, selectedSeason, setSelectedSeason, selectedGrade, setSelectedGrade, finalsOnly, setFinalsOnly, loading: clubLoading } = useClubData(orgId)

  const [players, setPlayers] = useState([])
  const [battingStats, setBattingStats] = useState({})
  const [bowlingStats, setBowlingStats] = useState({})
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')

  useEffect(() => {
    if (!orgId) return
    setLoading(true)
    api.listPlayers(orgId)
      .then(setPlayers)
      .catch(() => setPlayers([]))
      .finally(() => setLoading(false))
  }, [orgId])

  useEffect(() => {
    if (!orgId) return
    api.battingLeaderboard(orgId, { seasonId: selectedSeason, gradeId: selectedGrade, limit: 5000, finalsOnly })
      .then(rows => {
        const map = {}
        rows.forEach(r => { map[r.player_id] = r })
        setBattingStats(map)
      })
      .catch(() => {})
    api.bowlingLeaderboard(orgId, { seasonId: selectedSeason, gradeId: selectedGrade, limit: 5000, finalsOnly })
      .then(rows => {
        const map = {}
        rows.forEach(r => { map[r.player_id] = r })
        setBowlingStats(map)
      })
      .catch(() => {})
  }, [orgId, selectedSeason, selectedGrade, finalsOnly])

  const filtered = useMemo(() => {
    if (!search.trim()) return players
    return players.filter(p => nameMatchesSearch(p.display_name || p.name, search))
  }, [players, search])

  if (locked) return <ClubPinGate slug={clubSlug} lockInfo={locked} unlock={unlock} requestAccess={requestAccess} />
  if (inactive) return <ClubInactive slug={clubSlug} />
  if (notFound) return <ClubInactive variant="notfound" slug={clubSlug} />
  if (clubLoading) return <PbSpinner message="Loading players…" />

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1300px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <PageHeader
          eyebrow={org?.name ? `${org.name.toUpperCase()} · SQUAD` : 'SQUAD'}
          title="Players."
          meta={[<span key="c">{filtered.length} players</span>]}
          actions={
            <Link
              to={`/${clubSlug}/compare`}
              className="px-4 py-2 rounded font-mono text-[11px] tracking-wide2 font-semibold transition text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}
            >
              COMPARE
            </Link>
          }
        />

        {/* Search + filters */}
        <div className="flex flex-wrap gap-3 mb-5 items-center">
          <div className="relative w-full sm:flex-1 sm:min-w-[200px]">
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-pb-faint" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="text"
              placeholder="Search players…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full bg-pb-surface border pb-hairline text-pb-text text-sm rounded pl-9 pr-9 py-2 focus:outline-none focus:border-pb-accent placeholder-pb-faint"
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-pb-faint hover:text-pb-text text-lg leading-none"
              >
                ×
              </button>
            )}
          </div>
          <SeasonSelector
            seasons={seasons}
            grades={grades}
            selectedSeason={selectedSeason}
            setSelectedSeason={setSelectedSeason}
            selectedGrade={selectedGrade}
            setSelectedGrade={setSelectedGrade}
            finalsOnly={finalsOnly}
            setFinalsOnly={setFinalsOnly}
          />
        </div>

        {loading ? <PbSpinner /> : (
          <>
            {/* Mobile card view */}
            <div className="md:hidden space-y-2">
              {filtered.length === 0 ? (
                <Card>
                  <div className="py-8 text-center text-pb-faint text-sm">
                    {search ? `No players matching "${search}"` : 'No players found.'}
                  </div>
                </Card>
              ) : filtered.map(player => {
                const b = battingStats[player.id]
                const bw = bowlingStats[player.id]
                const bestFigs = bw?.best_bowling_figures
                  ? bw.best_bowling_figures.replace('-', '/')
                  : (bw?.best_figures_wickets != null ? `${fmtCount(bw.best_figures_wickets)} wickets` : null)
                return (
                  <Link
                    key={player.id}
                    to={`/players/${player.id}`}
                    className="block bg-pb-surface pb-hairline rounded p-3 active:bg-pb-surface2 hover:bg-pb-surface2 transition"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-pb-text font-semibold text-[15px] truncate pr-2">
                        {fmt(player.display_name || player.name)}
                      </span>
                      <span className="font-mono text-[10px] text-pb-faint shrink-0">VIEW →</span>
                    </div>
                    <div className="grid grid-cols-5 gap-x-2 gap-y-1.5 text-[11px]">
                      <PlayerStat label="M" value={b?.games != null ? fmtCount(b.games) : null} />
                      <PlayerStat label="INN" value={b?.innings} />
                      <PlayerStat label="RUNS" value={b?.total_runs != null ? fmtCount(b.total_runs) : null} accent />
                      <PlayerStat label="AVG" value={b?.average != null ? fmt2(b.average) : null} />
                      <PlayerStat label="HS" value={b?.high_score} />
                      <PlayerStat label="50s" value={b?.fifties} />
                      <PlayerStat label="WKTS" value={bw?.total_wickets != null ? fmtCount(bw.total_wickets) : null} accent={bw?.total_wickets > 0} />
                      <PlayerStat label="BEST" value={bestFigs} />
                    </div>
                  </Link>
                )
              })}
            </div>

            {/* Desktop table view */}
            <div className="hidden md:block">
              <Card pad="p-0">
                <div className="overflow-x-auto pb-scroll">
                  <table className="w-full min-w-[760px] text-[14px]">
                    <thead>
                      <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left bg-pb-surface2/40">
                        <th className="font-medium py-3 pl-5">PLAYER</th>
                        <th className="font-medium py-3 text-right">M</th>
                        <th className="font-medium py-3 text-right">INN</th>
                        <th className="font-medium py-3 text-right" style={{ color: 'var(--pb-accent)' }}>RUNS</th>
                        <th className="font-medium py-3 text-right">AVG</th>
                        <th className="font-medium py-3 text-right">HS</th>
                        <th className="font-medium py-3 text-right hidden md:table-cell">50s</th>
                        <th className="font-medium py-3 text-right hidden lg:table-cell" style={{ color: 'var(--pb-accent)' }}>WKTS</th>
                        <th className="font-medium py-3 text-right hidden lg:table-cell">BEST</th>
                        <th className="font-medium py-3 pr-5 w-16"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {filtered.length === 0 ? (
                        <tr>
                          <td colSpan={10} className="py-12 text-center text-pb-faint text-sm">
                            {search ? `No players matching "${search}"` : 'No players found.'}
                          </td>
                        </tr>
                      ) : filtered.map((player, i) => {
                        const b = battingStats[player.id]
                        const bw = bowlingStats[player.id]
                        const bestFigs = bw?.best_bowling_figures
                          ? bw.best_bowling_figures.replace('-', '/')
                          : (bw?.best_figures_wickets != null ? `${fmtCount(bw.best_figures_wickets)} wickets` : null)
                        return (
                          <tr key={player.id} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                            <td className="py-3 pl-5">
                              <Link to={`/players/${player.id}`} className="text-pb-text font-semibold hover:text-pb-accent transition-colors">
                                {fmt(player.display_name || player.name)}
                              </Link>
                            </td>
                            <td className="py-3 font-mono text-pb-dim text-right">{b?.games != null ? fmtCount(b.games) : '—'}</td>
                            <td className="py-3 font-mono text-pb-dim text-right">{b?.innings ?? '—'}</td>
                            <td className="py-3 text-right">
                              <span className="font-mono font-bold pb-num" style={{ color: 'var(--pb-accent)' }}>
                                {b?.total_runs != null ? fmtCount(b.total_runs) : '—'}
                              </span>
                            </td>
                            <td className="py-3 font-mono text-pb-dim text-right">{b?.average != null ? fmt2(b.average) : '—'}</td>
                            <td className="py-3 font-mono text-pb-dim text-right">{b?.high_score ?? '—'}</td>
                            <td className="py-3 font-mono text-pb-dim text-right hidden md:table-cell">{b?.fifties ?? '—'}</td>
                            <td className="py-3 text-right hidden lg:table-cell">
                              <span className="font-mono font-bold pb-num" style={{ color: bw?.total_wickets > 0 ? 'var(--pb-accent)' : undefined }}>
                                {bw?.total_wickets != null ? fmtCount(bw.total_wickets) : '—'}
                              </span>
                            </td>
                            <td className="py-3 font-mono text-pb-dim text-right hidden lg:table-cell">
                              {bestFigs ?? '—'}
                            </td>
                            <td className="py-3 pr-5 text-right">
                              <Link to={`/players/${player.id}`} className="font-mono text-[10px] text-pb-faint hover:text-pb-accent">
                                VIEW →
                              </Link>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </Card>
            </div>
          </>
        )}
      </main>
    </div>
  )
}
