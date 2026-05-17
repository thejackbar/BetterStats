import { useParams, Link } from 'react-router-dom'
import { useState, useEffect, useMemo } from 'react'
import { useClubData } from '../hooks/useClubData'
import { useClub } from '../hooks/useClub'
import { useClubTheme } from '../hooks/useClubTheme'
import { usePageMeta } from '../hooks/usePageMeta'
import { api } from '../lib/api'
import ClubInactive from './ClubInactive'
import SeasonSelector from '../components/SeasonSelector'
import { Card, PageHeader, PbSpinner } from '../lib/presskit'

function ResultPill({ result }) {
  if (!result) return null
  const styles = {
    WIN:  'bg-green-500/15 text-green-400',
    LOSS: 'bg-red-500/15 text-red-400',
    DRAW: 'bg-pb-surface2 text-pb-dim',
  }
  const cls = styles[result] || 'bg-pb-surface2 text-pb-dim'
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-mono font-semibold tracking-wide ${cls}`}>
      {result}
    </span>
  )
}

function GameRow({ game }) {
  const date = game.played_at
    ? new Date(game.played_at + 'T00:00:00').toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
    : '—'

  return (
    <Link
      to={`/games/${game.id}`}
      className="flex items-center gap-3 py-3 px-4 hover:bg-pb-surface2 transition group pb-hairline-t first:border-t-0"
    >
      {/* Date */}
      <span className="w-28 shrink-0 font-mono text-[12px] text-pb-faint">{date}</span>

      {/* Teams */}
      <div className="flex-1 min-w-0">
        <span className="font-semibold text-[14px] text-pb-text group-hover:text-pb-accent transition truncate block">
          {game.home_team || '—'} <span className="font-normal text-pb-dim">vs</span> {game.away_team || '—'}
        </span>
      </div>

      {/* Result + winner */}
      <div className="flex items-center gap-3 shrink-0">
        {game.winning_team && (
          <span className="hidden sm:block font-mono text-[12px] text-pb-dim truncate max-w-[180px]">
            {game.winning_team} won
          </span>
        )}
        <ResultPill result={game.result} />
        <span className="text-pb-faint text-[12px] group-hover:text-pb-accent transition">→</span>
      </div>
    </Link>
  )
}

function GradeSection({ gradeName, games }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="mb-4">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-2.5 bg-pb-surface2/60 hover:bg-pb-surface2 transition rounded-t border border-pb-hairline"
      >
        <span className="font-mono text-[11px] font-semibold tracking-wide3 text-pb-faint uppercase">
          {gradeName}
        </span>
        <div className="flex items-center gap-3">
          <span className="font-mono text-[11px] text-pb-faint">{games.length} games</span>
          <span className="text-pb-faint text-[12px]">{open ? '▲' : '▼'}</span>
        </div>
      </button>
      {open && (
        <Card pad="p-0" className="rounded-t-none border-t-0">
          {games.map(g => <GameRow key={g.id} game={g} />)}
        </Card>
      )}
    </div>
  )
}

export default function GamesPage() {
  const { clubSlug } = useParams()
  const { club, orgId, inactive } = useClub(clubSlug)
  useClubTheme(club)
  usePageMeta({
    title: club?.name ? `${club.name} Games — BetterStats` : null,
    description: club?.name ? `Match results for ${club.name}.` : null,
    image: club?.logo_url || null,
  })

  if (inactive) return <ClubInactive />

  const {
    seasons, grades,
    selectedSeason, setSelectedSeason,
    selectedGrade, setSelectedGrade,
    loading: clubLoading,
  } = useClubData(orgId)

  const [games, setGames] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!orgId) return
    setLoading(true)
    api.getOrgResults(orgId, { seasonId: selectedSeason, gradeId: selectedGrade })
      .then(setGames)
      .catch(() => setGames([]))
      .finally(() => setLoading(false))
  }, [orgId, selectedSeason, selectedGrade])

  // Group by grade_name, preserving played_at DESC order within each group
  const byGrade = useMemo(() => {
    const map = new Map()
    for (const g of games) {
      const key = g.grade_name || 'Unknown Grade'
      if (!map.has(key)) map.set(key, [])
      map.get(key).push(g)
    }
    // Sort grades numerically by leading digit, then alphabetically
    const gradeKey = name => {
      const m = name.match(/^(\d+)/)
      return m ? [parseInt(m[1], 10), name] : [Infinity, name]
    }
    return Array.from(map.entries()).sort(([a], [b]) => {
      const [an, as] = gradeKey(a)
      const [bn, bs] = gradeKey(b)
      return an !== bn ? an - bn : as.localeCompare(bs)
    })
  }, [games])

  const currentSeason = seasons?.find(s => s.id === selectedSeason)
  const seasonLabel = currentSeason?.name || 'ALL SEASONS'

  if (clubLoading) return <PbSpinner message="Loading club data…" />

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1300px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <PageHeader
          eyebrow={`MATCH RESULTS · ${seasonLabel.toUpperCase()}`}
          title="Games."
          meta={[<span key="s">{games.length > 0 ? `${games.length} results` : 'All grades, all seasons.'}</span>]}
        />

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

        {loading ? (
          <PbSpinner />
        ) : byGrade.length === 0 ? (
          <p className="text-pb-faint text-sm py-8 text-center">No games found for this selection.</p>
        ) : (
          byGrade.map(([gradeName, gradeGames]) => (
            <GradeSection key={gradeName} gradeName={gradeName} games={gradeGames} />
          ))
        )}
      </main>
    </div>
  )
}
